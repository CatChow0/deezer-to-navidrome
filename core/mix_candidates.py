"""Tracks you do not have yet, found through Deezer's public API, for the playlists
that download. Tempo comes from each track's 30-second preview, measured before
anything is downloaded."""
import json
import logging
from collections import defaultdict
from dataclasses import dataclass

import requests

from core import audio_tempo, stats_db
from core.mix_taste import MIN_TEMPO_FIT, _FILLER, base_title

logger = logging.getLogger(__name__)

DAY = 86400
RELATED_CACHE_DAYS = 14
TOP_LIMIT = 30
DISCOVER_FROM_ARTISTS = 30
DISCOVER_RELEASE_SHARE = 1 / 3
RELEASES_WINDOW_DAYS = 60
MAX_PREVIEW_CHECKS = 80
SPARE_FACTOR = 2        # Spare tracks, for when a download fails.


@dataclass
class Candidate:
    deezer_id: str
    artist: str
    artist_key: str
    title: str
    album: str
    key: str
    base: str
    preview: str
    explicit: bool
    rank: int = 0
    bpm: float = None


def _api(path, params=None):
    from core.deezer import _public_api

    return _public_api(path, params)


def parse(item, album=""):
    artist = (item.get("artist") or {}).get("name") or ""
    title = item.get("title") or ""
    names = stats_db.split_artists(artist)
    if not item.get("id") or not names or not title or item.get("readable") is False:
        return None
    return Candidate(
        deezer_id=str(item["id"]), artist=artist, artist_key=stats_db.name_key(names[0]), title=title,
        album=(item.get("album") or {}).get("title") or album, key=stats_db.track_key(names, title),
        base=f"{stats_db.name_key(names[0])}|{base_title(title)}", preview=item.get("preview") or "",
        explicit=bool(item.get("explicit_lyrics")), rank=int(item.get("rank") or 0),
    )


def related_artists(conn, artist_id, now, api=_api) -> list:
    row = conn.execute("SELECT related, fetched_at FROM related_cache WHERE artist_id=?", (str(artist_id),)).fetchone()
    if row and now - row["fetched_at"] < RELATED_CACHE_DAYS * DAY:
        return json.loads(row["related"])
    data = (api(f"/artist/{artist_id}/related", {"limit": 20}) or {}).get("data") or []
    found = [{"id": str(a["id"]), "name": a.get("name") or ""} for a in data if a.get("id")]
    conn.execute("INSERT OR REPLACE INTO related_cache(artist_id, related, fetched_at) VALUES (?,?,?)",
                 (str(artist_id), json.dumps(found), int(now)))
    conn.commit()
    return found


def artist_top(artist_id, api=_api) -> list:
    data = (api(f"/artist/{artist_id}/top", {"limit": TOP_LIMIT}) or {}).get("data") or []
    return [c for c in map(parse, data) if c]


def preview_tempo(candidate):
    if not candidate.preview:
        return None
    try:
        response = requests.get(candidate.preview, timeout=20)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.info("No preview for %s: %s", candidate.deezer_id, e)
        return None
    return audio_tempo.data_tempo(response.content)


class Exclusions:
    """What may not be proposed: what you own, what is on trial or was refused."""

    def __init__(self, owned, known_ids=(), rejected_keys=(), played=None, never_played_only=False):
        self.keys = {t.key for t in owned} | set(rejected_keys)
        self.bases = {f"{t.artist_key}|{base_title(t.title)}" for t in owned}
        self.ids = {str(i) for i in known_ids}
        self.played = played or {}
        self.never_played_only = never_played_only

    def allows(self, candidate) -> bool:
        if candidate.deezer_id in self.ids or candidate.key in self.keys or candidate.base in self.bases:
            return False
        if _FILLER.search(candidate.title):
            return False
        return not (self.never_played_only and candidate.key in self.played)


def distinct_versions(candidates) -> list:
    """One per title. The explicit version wins, as it does everywhere in this app."""
    best = {}
    for candidate in candidates:
        known = best.get(candidate.base)
        if known is None or (candidate.explicit, candidate.rank) > (known.explicit, known.rank):
            best[candidate.base] = candidate
    return list(best.values())


def select(candidates, exclusions, want, per_artist, rng, seed_tempos=None, tempo=preview_tempo) -> list:
    """Up to `want` tracks plus spares, in the order to try them. A preview that
    shows a tempo far from the seed rules a track out; no preview does not."""
    allowed = [c for c in distinct_versions(candidates) if exclusions.allows(c)]
    keyed = [(rng.random() ** (1 / max(c.rank, 1)), i) for i, c in enumerate(allowed)]
    order = [allowed[i] for _, i in sorted(keyed, reverse=True)]
    target = want * SPARE_FACTOR
    chosen, counts, checks = [], defaultdict(int), 0
    for candidate in order:
        if len(chosen) >= target:
            break
        if counts[candidate.artist_key] >= per_artist:
            continue
        if seed_tempos and checks < MAX_PREVIEW_CHECKS:
            checks += 1
            candidate.bpm = tempo(candidate)
            fit = audio_tempo.tempo_fit(candidate.bpm, seed_tempos)
            if fit is not None and fit < MIN_TEMPO_FIT:
                continue
        chosen.append(candidate)
        counts[candidate.artist_key] += 1
    return chosen


def artist_ids(stats_conn) -> dict:
    """artist key -> Deezer id, from the lookups the history already made."""
    return {r["key"]: r["deezer_id"] for r in stats_conn.execute("SELECT key, deezer_id FROM artists WHERE deezer_id IS NOT NULL")}


def seed_pool(conn, seed, ids, now, api=_api) -> list:
    """For an artist seed, that artist. For a track or album, its artists and the
    ones Deezer says are close to its main artist."""
    main = ids.get(seed.artist_key)
    sources = [ids[a] for a in seed.artists if a in ids]
    if seed.kind != "artist" and main:
        try:
            sources += [a["id"] for a in related_artists(conn, main, now, api)]
        except Exception as e:
            logger.warning("No related artists for %s: %s", seed.label, e)
    pool = []
    for source in dict.fromkeys(sources):
        try:
            pool += artist_top(source, api)
        except Exception as e:
            logger.warning("No top tracks for artist %s: %s", source, e)
    return pool


def habit_pool(conn, taste, ids, now, api=_api) -> list:
    """Around what you listen to: top tracks of the artists closest to your favorites
    (the more of them point to one, the better), and of the favorites themselves."""
    favorites = sorted(taste.artist_score, key=lambda a: -taste.artist_score[a])[:DISCOVER_FROM_ARTISTS]
    closeness = defaultdict(float)
    for artist in favorites:
        if artist not in ids:
            continue
        try:
            for near in related_artists(conn, ids[artist], now, api):
                closeness[near["id"]] += taste.artist_score[artist]
        except Exception as e:
            logger.warning("No related artists for %s: %s", artist, e)
    pool = []
    nearest = sorted(closeness, key=lambda a: -closeness[a])[:DISCOVER_FROM_ARTISTS]
    for source in [*nearest, *[ids[a] for a in favorites[:10] if a in ids]]:
        try:
            pool += artist_top(source, api)
        except Exception as e:
            logger.warning("No top tracks for artist %s: %s", source, e)
    return pool


def release_pool(releases, now_date, api=_api, limit=20) -> list:
    """New tracks: the recent releases of the artists you follow, from the feed."""
    recent = [r for r in releases if not r.get("featured") and r.get("release_date", "") >= now_date]
    pool = []
    for release in recent[:limit]:
        try:
            data = (api(f"/album/{release['id']}/tracks", {"limit": 50}) or {}).get("data") or []
        except Exception as e:
            logger.warning("No tracks for release %s: %s", release.get("id"), e)
            continue
        pool += [c for c in (parse(item, release.get("title", "")) for item in data) if c]
    return pool
