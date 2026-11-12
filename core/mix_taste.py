"""What you listen to, as the generated playlists need it: a score for each track
and artist, the tracks, albums and artists that keep coming back (the seeds), and
the choice of tracks for a mix built around one of them.

No network and no file access here, so all of it can be tried on real data."""
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePath

from core import stats_db
from core.audio_tempo import tempo_fit
from core.stats_genres import genre_group

DAY = 86400
HALF_LIFE_DAYS = 60     # A play counts half as much after two months.

MIX_COUNT = 4
SEED_POOL = 8           # Seeds rotate among the strongest of each kind.
TRACK_SEED_MIN_PLAYS = 5
ALBUM_SEED_MIN_TRACKS, ALBUM_SEED_MIN_PLAYS = 4, 15
ARTIST_SEED_MIN_TRACKS, ARTIST_SEED_MIN_PLAYS = 8, 20
UNKNOWN_NAMES = {"", "unknown", "unknown artist", "unknown album", "various artists", "various"}

MIX_SIZE = 30
MIN_MIX_SIZE = 12       # Under this, a seed is not worth a playlist.
FAMILIAR_SHARE = 2 / 3
FAMILIAR_MIN_PLAYS = 2
PER_ARTIST = 2
PER_ALBUM_ARTIST = 4
ALBUM_ARTIST_BOOST = 5
SEED_GENRE_MIN_SHARE = 0.15
ARTIST_GENRE_FALLBACK_SHARE = 0.6
ARTIST_GENRE_MIN_TRACKS = 5     # A few mislabelled tracks must not decide for a whole artist.
UNKNOWN_GENRE_FACTOR = 0.25
UNKNOWN_TEMPO_FIT = 0.35
MIN_TEMPO_FIT = 0.1

FILLER_KEEP_PLAYS = 5   # An interlude you really play has earned its place.

_VERSION = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]|\s+[-+]\s+.*$")
_FILLER = re.compile(r"\b(skit|interlude|intro|outro)\b", re.I)


@dataclass
class Taste:
    track_score: dict
    track_plays: dict
    track_genre: dict
    artist_score: dict
    artist_genres: dict
    artist_genre_tracks: dict = field(default_factory=dict)


@dataclass
class OwnedTrack:
    key: str
    artist_key: str
    artist: str
    title: str
    album: str
    path: str
    duration: float = None
    bpm: float = None
    genre: str = None


@dataclass
class Seed:
    kind: str           # "track", "album" or "artist"
    key: str
    label: str
    artist_key: str     # Its main artist: two mixes never share one.
    score: float
    tracks: dict = field(default_factory=dict)      # track key -> weight
    artists: set = field(default_factory=set)
    genres: dict = field(default_factory=dict)      # genre group -> weight

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.key}"


def _weight(listened_at, now) -> float:
    return 0.5 ** (max(0, now - listened_at) / (HALF_LIFE_DAYS * DAY))


def _known(name) -> bool:
    return stats_db.name_key(name) not in UNKNOWN_NAMES


def base_title(title) -> str:
    """The title without version marks: "Song (Album V)" and "Song" are near
    duplicates, and one mix only wants one of them."""
    return stats_db.title_key(_VERSION.sub("", stats_db.clean_title(title)) or title)


def build_taste(conn, now) -> Taste:
    track_score, track_plays, artist_score = defaultdict(float), defaultdict(int), defaultdict(float)
    track_genre = {}
    artist_genres = defaultdict(lambda: defaultdict(float))
    genre_tracks = defaultdict(lambda: defaultdict(set))
    rows = conn.execute(
        "SELECT p.listened_at, t.key, t.genre, a.key AS artist_key FROM plays p"
        " JOIN tracks t ON t.id = p.track_id"
        " LEFT JOIN track_artists ta ON ta.track_id = t.id AND ta.position = 0"
        " LEFT JOIN artists a ON a.id = ta.artist_id"
    )
    for row in rows:
        weight = _weight(row["listened_at"], now)
        track_score[row["key"]] += weight
        track_plays[row["key"]] += 1
        group = genre_group(row["genre"])
        if group:
            track_genre[row["key"]] = group
        if row["artist_key"] is not None:
            artist_score[row["artist_key"]] += weight
            if group:
                artist_genres[row["artist_key"]][group] += weight
                genre_tracks[row["artist_key"]][group].add(row["key"])
    return Taste(dict(track_score), dict(track_plays), track_genre, dict(artist_score),
                 {artist: dict(groups) for artist, groups in artist_genres.items()},
                 {artist: {g: len(keys) for g, keys in groups.items()} for artist, groups in genre_tracks.items()})


def find_seeds(conn, now) -> dict:
    """The tracks, albums and artists that keep coming back, strongest first."""
    tracks, albums, artists = {}, {}, {}
    rows = conn.execute(
        "SELECT p.listened_at, t.key, t.title, t.genre, a.key AS artist_key, a.name AS artist,"
        " al.key AS album_key, al.title AS album, al.album_artist"
        " FROM plays p JOIN tracks t ON t.id = p.track_id"
        " JOIN track_artists ta ON ta.track_id = t.id AND ta.position = 0"
        " JOIN artists a ON a.id = ta.artist_id"
        " LEFT JOIN albums al ON al.id = p.album_id"
    )
    plays = defaultdict(int)

    def add(table, kind, key, label, artist_key, row, weight):
        seed = table.setdefault(key, Seed(kind, key, label, artist_key, 0.0))
        seed.score += weight
        seed.tracks[row["key"]] = seed.tracks.get(row["key"], 0) + weight
        group = genre_group(row["genre"])
        if group:
            seed.genres[group] = seed.genres.get(group, 0) + weight
        plays[(kind, key)] += 1

    for row in rows:
        if not _known(row["artist"]):
            continue
        weight = _weight(row["listened_at"], now)
        add(tracks, "track", row["key"], row["title"], row["artist_key"], row, weight)
        tracks[row["key"]].artists.add(row["artist_key"])
        add(artists, "artist", row["artist_key"], row["artist"], row["artist_key"], row, weight)
        artists[row["artist_key"]].artists.add(row["artist_key"])
        if row["album_key"] and _known(row["album"]):
            add(albums, "album", row["album_key"], row["album"], row["artist_key"], row, weight)
            album = albums[row["album_key"]]
            album.artists.add(row["artist_key"])
            for name in stats_db.split_artists(row["album_artist"]):
                if _known(name):
                    album.artists.add(stats_db.name_key(name))

    # Guests count as artists of the album too: that is what holds its style.
    for album in albums.values():
        marks = ",".join("?" * len(album.tracks))
        for row in conn.execute(
            f"SELECT DISTINCT a.key, a.name FROM tracks t JOIN track_artists ta ON ta.track_id = t.id"
            f" JOIN artists a ON a.id = ta.artist_id WHERE t.key IN ({marks})", list(album.tracks)
        ):
            if _known(row["name"]):
                album.artists.add(row["key"])

    def strongest(table, keep):
        return sorted((s for s in table.values() if keep(s)), key=lambda s: (-s.score, s.key))

    return {
        "track": strongest(tracks, lambda s: plays[("track", s.key)] >= TRACK_SEED_MIN_PLAYS),
        "album": strongest(albums, lambda s: len(s.tracks) >= ALBUM_SEED_MIN_TRACKS
                           and plays[("album", s.key)] >= ALBUM_SEED_MIN_PLAYS),
        "artist": strongest(artists, lambda s: len(s.tracks) >= ARTIST_SEED_MIN_TRACKS
                            and plays[("artist", s.key)] >= ARTIST_SEED_MIN_PLAYS),
    }


def choose_seeds(seeds, recent_ids=frozenset(), rng=None, count=MIX_COUNT) -> list:
    """At least one track, one album and one artist when they exist, never one
    artist twice, and nothing the last run used, so the mixes change every day."""
    pools = {
        kind: [s for s in found if s.id not in recent_ids][:SEED_POOL]
        for kind, found in seeds.items()
    }
    chosen, used_artists = [], set()

    def take(pool):
        options = [s for s in pool if s.artist_key not in used_artists]
        if not options:
            return False
        seed = rng.choices(options, weights=[s.score for s in options])[0]
        chosen.append(seed)
        used_artists.add(seed.artist_key)
        pool.remove(seed)
        return True

    def fill():
        while len(chosen) < count:
            options = [pool for pool in pools.values() if any(s.artist_key not in used_artists for s in pool)]
            if not options:
                break
            take(rng.choice(options))

    for kind in ("track", "album", "artist"):
        take(pools.get(kind, []))
    fill()
    if len(chosen) < count and recent_ids:
        # Too few seeds for a new set every day: the last run's come back,
        # rather than a day with fewer mixes, or none.
        taken = {s.id for s in chosen}
        pools = {kind: [s for s in found if s.id not in taken][:SEED_POOL] for kind, found in seeds.items()}
        fill()
    return chosen[:count]


def _is_under(path, folders) -> bool:
    parents = PurePath(path).parents
    return any(PurePath(folder) in parents for folder in folders)


def owned_tracks(entries, exclude_under=(), features=None) -> list:
    """The library index as distinct tracks. Files on trial are left out: a track
    is not "yours" until it has been kept. `features`: path -> (bpm, genre)."""
    features = features or {}
    owned = {}
    for entry in entries:
        path = entry.get("path")
        if not path or _is_under(path, exclude_under):
            continue
        artist = entry.get("tag_artist") or entry.get("parsed_artist") or ""
        title = entry.get("tag_title") or entry.get("parsed_title") or entry.get("parsed_track_title") or ""
        names = stats_db.split_artists(artist)
        if not names or not title or not _known(names[0]):
            continue
        key = stats_db.track_key(names, title)
        bpm, genre = features.get(path, (None, None))
        known = owned.get(key)
        if known is None or (bpm and not known.bpm):
            owned[key] = OwnedTrack(
                key=key, artist_key=stats_db.name_key(names[0]), artist=names[0], title=title,
                album=entry.get("tag_album") or "", path=path, duration=entry.get("duration"),
                bpm=bpm, genre=genre,
            )
    return list(owned.values())


def _genre_of(track, taste):
    """The track's own genre first. The artist's only when nearly all of what you
    play from them has that one, or a few odd tags would decide for all of them."""
    group = genre_group(track.genre) or taste.track_genre.get(track.key)
    if group:
        return group
    groups = taste.artist_genres.get(track.artist_key)
    if groups:
        name, weight = max(groups.items(), key=lambda item: item[1])
        known_tracks = taste.artist_genre_tracks.get(track.artist_key, {}).get(name, 0)
        if weight / sum(groups.values()) >= ARTIST_GENRE_FALLBACK_SHARE and known_tracks >= ARTIST_GENRE_MIN_TRACKS:
            return name
    return None


def _affinity(score) -> float:
    return math.sqrt(score) + 0.1


def _weighted_order(items, weights, rng) -> list:
    """Items in a random order where a heavier one tends to come first."""
    keyed = [(rng.random() ** (1 / max(weight, 1e-9)), index) for index, weight in enumerate(weights)]
    return [items[index] for _, index in sorted(keyed, reverse=True)]


class _Mix:
    def __init__(self, limit):
        self.limit = limit
        self.tracks, self.bases = {}, set()
        self.counts = defaultdict(int)

    def add(self, track) -> bool:
        base = f"{track.artist_key}|{base_title(track.title)}"
        if track.key in self.tracks or base in self.bases or self.counts[track.artist_key] >= self.limit(track):
            return False
        self.tracks[track.key] = track
        self.bases.add(base)
        self.counts[track.artist_key] += 1
        return True

    def fill(self, order, count) -> None:
        for track in order:
            if count <= 0:
                return
            if self.add(track):
                count -= 1


def _spread(tracks, rng, first=None) -> list:
    """Shuffled, keeping one artist's tracks apart: always continue with the
    artist that has the most left, other than the one just played."""
    by_artist = defaultdict(list)
    for track in rng.sample(tracks, len(tracks)):
        if track is not first:
            by_artist[track.artist_key].append(track)
    result = [first] if first else []
    last = first.artist_key if first else None
    while by_artist:
        options = [artist for artist in by_artist if artist != last] or list(by_artist)
        most = max(len(by_artist[artist]) for artist in options)
        last = rng.choice([artist for artist in options if len(by_artist[artist]) == most])
        result.append(by_artist[last].pop())
        if not by_artist[last]:
            del by_artist[last]
    return result


def _is_filler(track, taste) -> bool:
    return bool(_FILLER.search(track.title)) and taste.track_plays.get(track.key, 0) < FILLER_KEEP_PLAYS


def _suitability(track, taste, seed, seed_genres, seed_tempos, near=None):
    """How well a track goes with a seed; None when it does not belong at all."""
    if _is_filler(track, taste):
        return None
    factor = 1.0
    if seed_genres:
        genre = _genre_of(track, taste)
        if genre is None:
            # Only the seed's own artists, and those close to it, are trusted without a genre.
            if track.artist_key not in seed.artists and track.artist_key not in (near or {}):
                return None
            factor *= UNKNOWN_GENRE_FACTOR
        elif genre not in seed_genres:
            return None
    fit = tempo_fit(track.bpm, seed_tempos)
    if fit is None:
        factor *= UNKNOWN_TEMPO_FIT
    elif fit < MIN_TEMPO_FIT:
        return None
    else:
        factor *= fit
    if seed.kind == "album" and track.artist_key in seed.artists:
        factor *= ALBUM_ARTIST_BOOST
    return factor


def _orders(candidates, taste, rng):
    """The tracks you come back to, and those you barely played, each in a
    weighted random order."""
    familiar, fresh = [], []
    for track, suit in candidates:
        if taste.track_plays.get(track.key, 0) >= FAMILIAR_MIN_PLAYS:
            # Straight score: these are the tracks you really come back to.
            familiar.append((track, suit * (taste.track_score.get(track.key, 0) + 0.05)))
        else:
            fresh.append((track, suit * _affinity(taste.artist_score.get(track.artist_key, 0))))
    return (_weighted_order([t for t, _ in familiar], [w for _, w in familiar], rng),
            _weighted_order([t for t, _ in fresh], [w for _, w in fresh], rng))


def pick_for_seed(taste, seed, owned, recent=frozenset(), size=MIX_SIZE, rng=None, minimum=MIN_MIX_SIZE, near=None) -> list:
    """The mix around one seed. An artist mix is that artist: what you play, and
    what you barely played. A track or album mix looks for the same genre and
    tempo, with few tracks per artist, and an album's own artists first.

    `near` ({artist key: closeness}, from Deezer's related artists): a track or
    album mix takes those artists first, and genre and tempo alone only fill
    what is left. Without it, genre and tempo decide alone.

    About two thirds are tracks you come back to and one third tracks you own and
    barely played. A mix can be shorter than asked: better that than filling it
    with tracks that do not belong. Under `minimum` it returns nothing."""
    by_key = {track.key: track for track in owned}
    close, others = [], []
    if seed.kind == "artist":
        others = [(t, 1.0) for t in owned if t.artist_key == seed.artist_key]
        limit = lambda track: size
    else:
        near = near or {}
        total = sum(seed.genres.values())
        seed_genres = {g for g, w in seed.genres.items() if w / total >= SEED_GENRE_MIN_SHARE} if total else set()
        seed_tempos = [(by_key[k].bpm, w) for k, w in seed.tracks.items() if k in by_key]
        for track in owned:
            suit = _suitability(track, taste, seed, seed_genres, seed_tempos, near)
            if suit is None:
                continue
            if track.artist_key in near:
                close.append((track, suit * near[track.artist_key]))
            else:
                others.append((track, suit))
        if seed.kind == "album":
            limit = lambda track: PER_ALBUM_ARTIST if track.artist_key in seed.artists else PER_ARTIST
        else:
            limit = lambda track: PER_ARTIST

    not_recent = lambda order: [t for t in order if t.key not in recent]
    mix = _Mix(limit)
    first = by_key.get(seed.key) if seed.kind == "track" else None
    if first:
        mix.add(first)
    # The artists close to the seed first; the others only fill what is left.
    for group in (close, others):
        familiar_order, fresh_order = _orders(group, taste, rng)
        mix.fill(not_recent(familiar_order), round(size * FAMILIAR_SHARE) - len(mix.tracks))
        mix.fill(not_recent(fresh_order), size - len(mix.tracks))
        # Short of tracks: first the other kind, then what was recently proposed.
        mix.fill(not_recent(familiar_order), size - len(mix.tracks))
        mix.fill(familiar_order + fresh_order, size - len(mix.tracks))
    if len(mix.tracks) < minimum:
        return []
    return _spread(list(mix.tracks.values()), rng, first=first)
