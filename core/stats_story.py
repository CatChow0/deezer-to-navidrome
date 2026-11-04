"""What makes one recap different from the next: its obsessions, binges, movers
and listener personality, and which slides it is worth showing. Every number
comes from the plays; a slide with nothing true to say does not appear."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta

SESSION_GAP = 30 * 60
USUAL_MARGIN = 1.1
LOYALTY_FROM = 0.15
OBSESSION_FROM = 5
BINGE_FROM = 2 * 3600
ALBUM_RUN_TRACKS = 4
MOVER_FROM = 5
DROPPED_FROM = 5
MIN_SLIDES_TOTAL = 12
PERSONALITY_MIN_PLAYS = 20
FILM_SECONDS = 2 * 3600
FLIGHT_SECONDS = 14 * 3600
DAY_SECONDS = 24 * 3600

ALWAYS = {"intro", "top_artist", "personality", "time", "outro"}
ORDER = [
    "intro", "opener", "genres", "artist_countdown", "top_artist", "loyalty", "track_countdown", "top_track",
    "obsession", "binge", "album_run", "new_artists", "then_now", "biggest_month", "clock", "personality", "time", "outro",
]

_percent = lambda share: f"{round(share * 100)}%"  # noqa: E731


def _above(metrics, name, base) -> float:
    """How far a habit clears its bar. Your own usual sets the bar when it is
    higher, so a lifelong night owl only earns the title in an unusual month."""
    usual = metrics.get(f"usual_{name}")
    return metrics[name] / max(base, usual * USUAL_MARGIN if usual else 0)


# Name, how strongly these numbers fit (1 or more to qualify), and the reason
# shown with the title. The strongest fit wins, so months differ.
PERSONALITY_RULES = (
    ("One-Track Mind", lambda m: m["top_track_share"] / 0.08,
     lambda m: f"One song took {_percent(m['top_track_share'])} of your plays."),
    ("Obsessive", lambda m: m.get("obsession_plays", 0) / 25,
     lambda m: f"You played one song {m['obsession_plays']} times in a single day."),
    ("Superfan", lambda m: m["top_artist_share"] / 0.20,
     lambda m: f"One artist took {_percent(m['top_artist_share'])} of your plays."),
    ("Marathon Listener", lambda m: m.get("binge_hours", 0) / 10,
     lambda m: f"Your longest sitting lasted {m['binge_hours']:.0f} hours."),
    ("Comeback Kid", lambda m: m.get("comeback_plays", 0) / 100,
     lambda m: f"You went back to an old favorite for {m['comeback_plays']} plays."),
    ("Night Owl", lambda m: _above(m, "night_share", 0.35),
     lambda m: f"{_percent(m['night_share'])} of your plays happened between 22:00 and 05:00."),
    ("Early Bird", lambda m: _above(m, "morning_share", 0.25),
     lambda m: f"{_percent(m['morning_share'])} of your plays happened between 05:00 and 09:00."),
    ("Weekend Warrior", lambda m: _above(m, "weekend_share", 0.45),
     lambda m: f"{_percent(m['weekend_share'])} of your plays landed on a weekend."),
    ("Explorer", lambda m: m["new_artist_share"] / 0.25 if m["has_previous"] else 0,
     lambda m: f"{_percent(m['new_artist_share'])} of your artists were completely new to you."),
    ("Genre Hopper", lambda m: (m["genre_count"] / 6) if m["genre_pct"] >= 50 and m["top_genre_share"] <= 0.40 else 0,
     lambda m: f"{m['genre_count']} genres, and none of them took more than {_percent(m['top_genre_share'])}."),
    ("Album Purist", lambda m: m["top_albums_share"] / 0.40,
     lambda m: f"Five albums took {_percent(m['top_albums_share'])} of your plays."),
)


def personality(metrics) -> dict:
    if metrics["plays"] < PERSONALITY_MIN_PLAYS:
        return {"name": "Just Warming Up", "reason": f"Only {metrics['plays']:,} plays so far. The story is just starting."}
    best = max(PERSONALITY_RULES, key=lambda rule: rule[1](metrics))
    if best[1](metrics) >= 1:
        return {"name": best[0], "reason": best[2](metrics)}
    return {"name": "Steady Listener", "reason": f"{metrics['plays']:,} plays, spread evenly with no single obsession."}


def _track_row(row) -> dict:
    return {"id": row["id"], "title": row["title"], "artist": row["artist"], "duration": row["duration"] or 0,
            "deezer_track_id": row["deezer_track_id"] or "", "image": f"/stats/cover/track/{row['id']}"}


def _load_track(conn, track_id):
    row = conn.execute(
        "SELECT id, title, artist_display artist, duration_sec duration, deezer_track_id FROM tracks WHERE id = ?", (track_id,),
    ).fetchone()
    return _track_row(row) if row else None


def _artist_top_track(conn, artist_id, start, end):
    """That artist's own most-played track in the period, by credit and not by name."""
    row = conn.execute(
        "SELECT p.track_id FROM plays p JOIN track_artists ta ON ta.track_id = p.track_id"
        " WHERE ta.artist_id = ? AND p.listened_at >= ? AND p.listened_at < ?"
        " GROUP BY p.track_id ORDER BY COUNT(*) DESC, p.track_id LIMIT 1",
        (artist_id, start, end),
    ).fetchone()
    return _load_track(conn, row[0]) if row else None


def _artist_counts(conn, start, end) -> dict:
    return {row[0]: row[1] for row in conn.execute(
        "SELECT ta.artist_id, COUNT(*) FROM plays p JOIN track_artists ta ON ta.track_id = p.track_id"
        " WHERE p.listened_at >= ? AND p.listened_at < ? GROUP BY ta.artist_id", (start, end),
    )}


def _artist_card(conn, artist_id, **extra) -> dict:
    name = conn.execute("SELECT name FROM artists WHERE id = ?", (artist_id,)).fetchone()[0]
    return {"id": artist_id, "name": name, "image": f"/stats/cover/artist/{artist_id}", **extra}


def _sessions(plays) -> list:
    """Runs of plays with gaps under half an hour."""
    sessions, current = [], []
    for play in plays:
        if current and play["listened_at"] - current[-1]["listened_at"] > SESSION_GAP:
            sessions.append(current)
            current = []
        current.append(play)
    if current:
        sessions.append(current)
    return sessions


def _binge(conn, sessions, zone):
    def length(session):
        return session[-1]["listened_at"] - session[0]["listened_at"] + int(session[-1]["seconds"] or 0)

    if not sessions:
        return None
    longest = max(sessions, key=length)
    seconds = length(longest)
    if seconds < BINGE_FROM:
        return None
    tracks = [play["track_id"] for play in longest]
    credits = Counter()
    for track_id in tracks:
        names = conn.execute(
            "SELECT a.name FROM track_artists ta JOIN artists a ON a.id = ta.artist_id WHERE ta.track_id = ? ORDER BY ta.position LIMIT 1", (track_id,),
        ).fetchone()
        if names:
            credits[names[0]] += 1
    return {
        "date": datetime.fromtimestamp(longest[0]["listened_at"], zone).date().isoformat(),
        "seconds": seconds, "plays": len(longest),
        "top_artist": credits.most_common(1)[0][0] if credits else "",
        "track_id": Counter(tracks).most_common(1)[0][0],
    }


def _album_run(conn, sessions, zone):
    best = None
    for session in sessions:
        by_album = defaultdict(set)
        for play in session:
            if play["album_id"]:
                by_album[play["album_id"]].add(play["track_id"])
        for album_id, tracks in by_album.items():
            if len(tracks) < ALBUM_RUN_TRACKS or (best and len(tracks) <= best["tracks"]):
                continue
            total = conn.execute("SELECT COUNT(DISTINCT track_id) FROM plays WHERE album_id = ?", (album_id,)).fetchone()[0]
            if len(tracks) * 2 < total:
                continue
            row = conn.execute("SELECT title, album_artist FROM albums WHERE id = ?", (album_id,)).fetchone()
            best = {
                "id": album_id, "title": row["title"], "artist": row["album_artist"], "tracks": len(tracks), "of": total,
                "date": datetime.fromtimestamp(session[0]["listened_at"], zone).date().isoformat(),
                "image": f"/stats/cover/album/{album_id}", "track_id": sorted(tracks)[0],
            }
    return best


def _obsession(conn, plays, zone):
    days = Counter()
    for play in plays:
        days[(datetime.fromtimestamp(play["listened_at"], zone).date(), play["track_id"])] += 1
    if not days:
        return None
    (day, track_id), count = max(days.items(), key=lambda item: (item[1], item[0][0]))
    if count < OBSESSION_FROM:
        return None
    color = conn.execute(
        "SELECT c.color FROM covers c JOIN tracks t ON c.kind = 'track' AND c.item_key = t.key WHERE t.id = ?", (track_id,),
    ).fetchone()
    return {**_load_track(conn, track_id), "date": day.isoformat(), "plays": count, "color": color[0] if color else ""}


def _comparisons(seconds) -> list:
    items = (("films", FILM_SECONDS), ("flights from Paris to Tokyo", FLIGHT_SECONDS), ("days of non-stop music", DAY_SECONDS))
    return [{"value": seconds // size, "unit": unit} for unit, size in items if seconds // size >= 1]


def _clock(plays, zone) -> dict:
    hours = [0] * 24
    for play in plays:
        hours[datetime.fromtimestamp(play["listened_at"], zone).hour] += 1
    return {"hours": hours, "peak_hour": max(range(24), key=lambda h: (hours[h], -h))}


def _then_and_now(conn, data, start, previous_start, previous_end, end) -> tuple:
    """(movers, comeback, dropped): they only mean something between whole periods."""
    unknown = {row[0] for row in conn.execute("SELECT id FROM artists WHERE name LIKE '[Unknown%'")}
    now = {a: n for a, n in _artist_counts(conn, start, end).items() if a not in unknown}
    before = {a: n for a, n in _artist_counts(conn, previous_start, previous_end).items() if a not in unknown}
    deltas = {artist: now[artist] - before[artist] for artist in now if artist in before}
    rise = max(deltas, key=lambda a: (deltas[a], -a), default=None)
    fall = min(deltas, key=lambda a: (deltas[a], a), default=None)
    movers = {
        "rise": _artist_card(conn, rise, delta=deltas[rise], plays=now[rise]) if rise and deltas[rise] >= MOVER_FROM else None,
        "fall": _artist_card(conn, fall, delta=deltas[fall], plays=now[fall]) if fall and deltas[fall] <= -MOVER_FROM else None,
    }
    if not movers["rise"] and not movers["fall"]:
        movers = None

    comeback = None
    candidates = sorted((a for a in now if a not in before), key=lambda a: (-now[a], a))
    for artist in candidates:
        earlier = conn.execute(
            "SELECT 1 FROM plays p JOIN track_artists ta ON ta.track_id = p.track_id WHERE ta.artist_id = ? AND p.listened_at < ? LIMIT 1",
            (artist, previous_start),
        ).fetchone()
        if earlier:
            comeback = _artist_card(conn, artist, plays=now[artist])
            break

    dropped = None
    gone = sorted((a for a in before if a not in now and before[a] >= DROPPED_FROM), key=lambda a: (-before[a], a))
    if gone:
        dropped = _artist_card(conn, gone[0], previous_plays=before[gone[0]])
    return movers, comeback, dropped


def _biggest_month(plays, zone, kind):
    if kind != "year" or not plays:
        return None
    months = Counter()
    for play in plays:
        local = datetime.fromtimestamp(play["listened_at"], zone)
        months[(local.year, local.month)] += 1
    (year, month), count = max(months.items(), key=lambda item: (item[1], item[0]))
    return {"label": f"{datetime(year, month, 1):%B} {year}", "plays": count}


def _time_shares(moments, zone) -> dict:
    night = morning = weekend = 0
    for moment in moments:
        local = datetime.fromtimestamp(moment, zone)
        night += local.hour >= 22 or local.hour < 5
        morning += 5 <= local.hour < 9
        weekend += local.weekday() >= 5
    total = len(moments) or 1
    return {"night_share": night / total, "morning_share": morning / total, "weekend_share": weekend / total}


def _metrics(conn, data, plays, zone, story) -> dict:
    total = data["totals"]["plays"]
    share = lambda part: part / total if total else 0  # noqa: E731
    times = _time_shares([play["listened_at"] for play in plays], zone)
    usual = _time_shares([row[0] for row in conn.execute("SELECT listened_at FROM plays")], zone)
    top = data["top"]
    new_artists = len(data["new_artists"])
    return {
        **times,
        **{f"usual_{name}": value for name, value in usual.items()},
        "obsession_plays": story["obsession"]["plays"] if story["obsession"] else 0,
        "binge_hours": story["binge"]["seconds"] / 3600 if story["binge"] else 0,
        "comeback_plays": story["comeback"]["plays"] if story["comeback"] else 0,
        "plays": total,
        "top_track_share": share(top["tracks"][0]["plays"]) if top["tracks"] else 0,
        "top_artist_share": share(top["artists"][0]["plays"]) if top["artists"] else 0,
        "new_artist_share": new_artists / data["totals"]["artists"] if data["totals"]["artists"] else 0,
        "has_previous": data["has_previous"],
        "genre_count": len(data["genres"]),
        "top_genre_share": data["genres"][0]["share"] if data["genres"] else 1,
        "genre_pct": data["coverage"]["genre_pct"],
        "top_albums_share": share(sum(album["plays"] for album in top["albums"][:5])),
    }


def _named_artists(data) -> list:
    """Top artists, without the placeholder tags give untagged files."""
    return [artist for artist in data["top"]["artists"] if not artist["name"].startswith("[Unknown")]


def _pick_slides(story, data) -> list:
    """The always-there frame, then this period's strongest stories."""
    top = {"artists": _named_artists(data), "tracks": data["top"]["tracks"]}
    plays = data["totals"]["plays"]
    if not plays:
        return ["intro", "outro"]
    scores = {}
    if story["opener"]:
        scores["opener"] = 0.4
    if len(data["genres"]) >= 2:
        scores["genres"] = 1.0
    if len(top["tracks"]) >= 3:
        scores["track_countdown"] = 0.8
    if story["loyalty"]:
        scores["loyalty"] = story["loyalty"]["percent"] / 20
    if story["obsession"]:
        scores["obsession"] = story["obsession"]["plays"] / 12
    if story["binge"]:
        scores["binge"] = story["binge"]["seconds"] / (8 * 3600)
    if story["album_run"]:
        scores["album_run"] = story["album_run"]["tracks"] / 20
    if data["new_artists"]:
        scores["new_artists"] = min(len(data["new_artists"]) / 3, 2)
    if story["movers"] or story["comeback"] or story["dropped"]:
        scores["then_now"] = 1.2
    if story["biggest_month"]:
        scores["biggest_month"] = 1.0
    if plays >= PERSONALITY_MIN_PLAYS:
        scores["clock"] = 0.6

    chosen = set(ALWAYS)
    if not top["artists"]:
        chosen.discard("top_artist")
    if len(top["artists"]) >= 3:
        chosen.add("artist_countdown")
    if top["tracks"] and top["tracks"][0]["plays"] >= 2:
        chosen.add("top_track")
    room = MIN_SLIDES_TOTAL - len(chosen)
    chosen |= set(sorted(scores, key=lambda name: (-scores[name], ORDER.index(name)))[:room])
    return [name for name in ORDER if name in chosen]


def _slide_tracks(conn, story, data, start, end) -> dict:
    """The song behind each slide: that slide's subject when it has one."""
    top = {"artists": _named_artists(data), "tracks": data["top"]["tracks"]}
    first_track = _load_track(conn, top["tracks"][0]["id"]) if top["tracks"] else None
    second_track = _load_track(conn, top["tracks"][1]["id"]) if len(top["tracks"]) > 1 else first_track
    artist_song = lambda artist: _artist_top_track(conn, artist["id"], start, end) if artist else None  # noqa: E731
    movers = story["movers"] or {}
    binge = story["binge"]
    return {
        "intro": second_track,
        "opener": _load_track(conn, story["opener"]["id"]) if story["opener"] else None,
        "artist_countdown": artist_song(top["artists"][1]) if len(top["artists"]) > 1 else None,
        "top_artist": artist_song(top["artists"][0]) if top["artists"] else None,
        "loyalty": artist_song(top["artists"][0]) if top["artists"] else None,
        "track_countdown": second_track,
        "top_track": first_track,
        "obsession": _load_track(conn, story["obsession"]["id"]) if story["obsession"] else None,
        "binge": _load_track(conn, binge["track_id"]) if binge else None,
        "album_run": _load_track(conn, story["album_run"]["track_id"]) if story["album_run"] else None,
        "new_artists": artist_song(data["discovery"]) if data["discovery"] else None,
        "then_now": artist_song(movers.get("rise")) or artist_song(story["comeback"]),
    }


def build_story(conn, data, start, end, previous_start, previous_end, zone) -> dict:
    plays = [dict(row) for row in conn.execute(
        "SELECT p.listened_at, p.track_id, p.album_id, COALESCE(p.duration_sec, t.duration_sec, 0) seconds"
        " FROM plays p JOIN tracks t ON t.id = p.track_id WHERE p.listened_at >= ? AND p.listened_at < ?"
        " ORDER BY p.listened_at", (start, end),
    )]
    sessions = _sessions(plays)
    totals = data["totals"]

    opener = None
    if plays:
        first = datetime.fromtimestamp(plays[0]["listened_at"], zone)
        opener = {**_load_track(conn, plays[0]["track_id"]), "date": first.date().isoformat(), "time": first.strftime("%H:%M")}

    loyalty = None
    artists = _named_artists(data)
    if artists and totals["plays"]:
        artist = artists[0]
        share = artist["plays"] / totals["plays"]
        if share >= LOYALTY_FROM:
            loyalty = {"artist": artist, "percent": round(share * 100), "one_in": round(1 / share)}

    movers = comeback = dropped = None
    if data["has_previous"] and not data["so_far"]:
        movers, comeback, dropped = _then_and_now(conn, data, start, previous_start, previous_end, end)

    story = {
        "top_artists": artists,
        "opener": opener,
        "loyalty": loyalty,
        "obsession": _obsession(conn, plays, zone),
        "binge": _binge(conn, sessions, zone),
        "album_run": _album_run(conn, sessions, zone),
        "movers": movers,
        "comeback": comeback,
        "dropped": dropped,
        "comparisons": _comparisons(totals["seconds"]),
        "clock": _clock(plays, zone),
        "biggest_month": _biggest_month(plays, zone, data["kind"]),
    }
    story["personality"] = personality(_metrics(conn, data, plays, zone, story))
    names = _pick_slides(story, data)
    tracks = _slide_tracks(conn, story, data, start, end)
    fallback = _load_track(conn, data["top"]["tracks"][0]["id"]) if data["top"]["tracks"] else None
    story["slides"] = [{"type": name, "track": tracks.get(name) or fallback} for name in names]
    return story
