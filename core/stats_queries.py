"""Every number the Stats tab shows. Recaps are built on overview(), so a recap
and the charts for the same period cannot disagree."""
import calendar
import math
import re
import time
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core import stats_db
from core.stats_genres import genre_group

_SECONDS = "COALESCE(p.duration_sec, t.duration_sec, 0)"
TOP_SIZE = 10


class BadPeriod(ValueError):
    """A period, key, timezone or kind the client should not have sent."""


def _zone(tz):
    if not tz or not isinstance(tz, str):
        raise BadPeriod("Unknown timezone")
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError) as e:
        raise BadPeriod("Unknown timezone") from e


def _week_monday(key) -> date:
    match = re.fullmatch(r"(\d{4})-W(\d{2})", key or "")
    if not match:
        raise BadPeriod("Expected a week like 2026-W43")
    try:
        return date.fromisocalendar(int(match[1]), int(match[2]), 1)
    except ValueError as e:
        raise BadPeriod("No such week") from e


def _month_parts(key) -> tuple:
    match = re.fullmatch(r"(\d{4})-(\d{2})", key or "")
    if not match or not 1 <= int(match[2]) <= 12 or int(match[1]) < 1:
        raise BadPeriod("Expected a month like 2026-10")
    return int(match[1]), int(match[2])


def _year(key) -> int:
    if not re.fullmatch(r"\d{4}", key or "") or int(key) < 1:
        raise BadPeriod("Expected a year like 2026")
    return int(key)


def _period_dates(period, key) -> tuple:
    """First day and the day after the last, or (None, None) for all time."""
    if period == "all":
        if key:
            raise BadPeriod("All time takes no key")
        return None, None
    if period == "week":
        monday = _week_monday(key)
        return monday, monday + timedelta(days=7)
    if period == "month":
        year, month = _month_parts(key)
        return date(year, month, 1), date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    if period == "year":
        year = _year(key)
        return date(year, 1, 1), date(year + 1, 1, 1)
    raise BadPeriod("Unknown period")


def _local_midnight(day, zone) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=zone).timestamp())


def period_bounds(period, key, tz) -> tuple:
    zone = _zone(tz)
    try:
        first, after = _period_dates(period, key)
    except (ValueError, OverflowError) as e:
        raise BadPeriod(str(e)) from e
    if first is None:
        return None, None
    return _local_midnight(first, zone), _local_midnight(after, zone)


def previous_key(period, key):
    if period == "all":
        return None
    if period == "week":
        iso = (_week_monday(key) - timedelta(days=7)).isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if period == "month":
        year, month = _month_parts(key)
        return f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"
    if period == "year":
        return f"{_year(key) - 1:04d}"
    raise BadPeriod("Unknown period")


def _label(period, key) -> str:
    if period == "all":
        return "All time"
    if period == "week":
        year, week = key.split("-W")
        return f"Week {int(week)}, {year}"
    if period == "month":
        year, month = _month_parts(key)
        return f"{calendar.month_name[month]} {year}"
    return key


def _where(start, end) -> tuple:
    if start is None:
        return "1=1", ()
    return "p.listened_at >= ? AND p.listened_at < ?", (start, end)


def _totals(conn, start, end) -> dict:
    where, args = _where(start, end)
    row = conn.execute(
        f"SELECT COUNT(*) plays, COALESCE(SUM({_SECONDS}), 0) seconds,"
        " COUNT(DISTINCT p.album_id) albums, COUNT(DISTINCT p.track_id) tracks"
        f" FROM plays p JOIN tracks t ON t.id = p.track_id WHERE {where}", args,
    ).fetchone()
    artists = conn.execute(
        f"SELECT COUNT(DISTINCT ta.artist_id) FROM plays p JOIN track_artists ta ON ta.track_id = p.track_id WHERE {where}", args,
    ).fetchone()[0]
    return {"plays": row["plays"], "seconds": int(round(row["seconds"])), "artists": artists,
            "albums": row["albums"], "tracks": row["tracks"]}


def _artist_rows(conn, start, end, limit=TOP_SIZE, only_new_since=False) -> list:
    where, args = _where(start, end)
    having = ""
    if only_new_since:
        having = "HAVING (SELECT MIN(p2.listened_at) FROM plays p2 JOIN track_artists ta2 ON ta2.track_id = p2.track_id WHERE ta2.artist_id = a.id) >= ?"
        args = (*args, start)
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    rows = conn.execute(
        f"SELECT a.id, a.name, a.picture_url image, COUNT(*) plays, SUM({_SECONDS}) seconds"
        " FROM plays p JOIN tracks t ON t.id = p.track_id"
        " JOIN track_artists ta ON ta.track_id = p.track_id JOIN artists a ON a.id = ta.artist_id"
        f" WHERE {where} GROUP BY a.id {having} ORDER BY plays DESC, a.name {limit_sql}", args,
    ).fetchall()
    return [{"id": r["id"], "name": r["name"], "plays": r["plays"], "seconds": int(round(r["seconds"])), "image": r["image"] or ""} for r in rows]


def _album_rows(conn, start, end, limit=TOP_SIZE) -> list:
    where, args = _where(start, end)
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    rows = conn.execute(
        f"SELECT al.id, al.title, al.album_artist artist, COALESCE(al.cover_url, MAX(t.cover_url)) image, COUNT(*) plays"
        " FROM plays p JOIN tracks t ON t.id = p.track_id JOIN albums al ON al.id = p.album_id"
        f" WHERE {where} GROUP BY al.id ORDER BY plays DESC, al.title {limit_sql}", args,
    ).fetchall()
    return [{"id": r["id"], "title": r["title"], "artist": r["artist"], "plays": r["plays"], "image": r["image"] or ""} for r in rows]


def _track_rows(conn, start, end, limit=TOP_SIZE) -> list:
    where, args = _where(start, end)
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    rows = conn.execute(
        f"SELECT t.id, t.title, t.artist_display artist, t.cover_url image, t.deezer_track_id, COUNT(*) plays, SUM({_SECONDS}) seconds"
        f" FROM plays p JOIN tracks t ON t.id = p.track_id WHERE {where}"
        f" GROUP BY t.id ORDER BY plays DESC, t.title {limit_sql}", args,
    ).fetchall()
    return [{"id": r["id"], "title": r["title"], "artist": r["artist"], "plays": r["plays"],
             "seconds": int(round(r["seconds"])), "image": r["image"] or "", "deezer_track_id": r["deezer_track_id"] or ""} for r in rows]


def _genres(conn, start, end, total_plays) -> tuple:
    """(rows, percentage of plays with a known genre)."""
    where, args = _where(start, end)
    groups = {}
    for row in conn.execute(
        f"SELECT t.genre, COUNT(*) plays, SUM({_SECONDS}) seconds FROM plays p JOIN tracks t ON t.id = p.track_id"
        f" WHERE {where} GROUP BY t.genre", args,
    ):
        name = genre_group(row["genre"])
        if name:
            entry = groups.setdefault(name, {"name": name, "plays": 0, "seconds": 0.0})
            entry["plays"] += row["plays"]
            entry["seconds"] += row["seconds"]
    known = sum(g["plays"] for g in groups.values())
    rows = sorted(groups.values(), key=lambda g: (-g["plays"], g["name"]))
    for row in rows:
        row["seconds"] = int(round(row["seconds"]))
        row["share"] = row["plays"] / known
    return rows, round(known * 100 / total_plays) if total_plays else 100


def _length_coverage(conn, start, end, total_plays) -> int:
    if not total_plays:
        return 100
    where, args = _where(start, end)
    known = conn.execute(
        f"SELECT COUNT(*) FROM plays p JOIN tracks t ON t.id = p.track_id WHERE {where} AND {_SECONDS} > 0", args,
    ).fetchone()[0]
    return round(known * 100 / total_plays)


def _habits(conn, start, end, zone) -> dict:
    where, args = _where(start, end)
    heatmap = [[0] * 24 for _ in range(7)]
    days = Counter()
    for (moment,) in conn.execute(f"SELECT p.listened_at FROM plays p WHERE {where}", args):
        local = datetime.fromtimestamp(moment, zone)
        heatmap[local.weekday()][local.hour] += 1
        days[local.date()] += 1

    busiest = {"date": "", "plays": 0}
    if days:
        day, plays = max(days.items(), key=lambda item: (item[1], item[0]))
        busiest = {"date": day.isoformat(), "plays": plays}

    streak = {"days": 0, "start": "", "end": ""}
    run_start = previous = None
    for day in sorted(days):
        if previous is None or day - previous != timedelta(days=1):
            run_start = day
        previous = day
        length = (day - run_start).days + 1
        if length > streak["days"]:
            streak = {"days": length, "start": run_start.isoformat(), "end": day.isoformat()}
    return {"heatmap": heatmap, "busiest_day": busiest, "longest_streak": streak}


def _overview(conn, period, key, tz) -> dict:
    start, end = period_bounds(period, key, tz)
    totals = _totals(conn, start, end)
    genres, genre_pct = _genres(conn, start, end, totals["plays"])
    return {
        "period": period,
        "key": key,
        "label": _label(period, key),
        "totals": totals,
        "coverage": {"length_pct": _length_coverage(conn, start, end, totals["plays"]), "genre_pct": genre_pct},
        "top": {
            "artists": _artist_rows(conn, start, end),
            "albums": _album_rows(conn, start, end),
            "tracks": _track_rows(conn, start, end),
        },
        "genres": genres,
        "habits": _habits(conn, start, end, _zone(tz)),
    }


def overview(period, key, tz) -> dict:
    with closing(stats_db.connect()) as conn:
        return _overview(conn, period, key, tz)


def recap(kind, key, tz) -> dict:
    if kind not in ("month", "year"):
        raise BadPeriod("Unknown recap")
    with closing(stats_db.connect()) as conn:
        data = _overview(conn, kind, key, tz)
        start, end = period_bounds(kind, key, tz)
        zone = _zone(tz)
        first_play = conn.execute("SELECT MIN(listened_at) FROM plays").fetchone()[0]
        has_previous = first_play is not None and first_play < start
        data["kind"] = kind
        data["has_previous"] = has_previous
        data["so_far"] = end > time.time()
        data["partial"] = (
            first_play is not None and start <= first_play < end
            and datetime.fromtimestamp(first_play, zone).date() > datetime.fromtimestamp(start, zone).date()
        )
        data["previous"] = None
        data["new_artists"] = []
        data["discovery"] = None
        counts = {"artists": {}, "albums": {}, "tracks": {}}
        if has_previous:
            prev_key = previous_key(kind, key)
            prev_start, prev_end = period_bounds(kind, prev_key, tz)
            data["previous"] = {"key": prev_key, "label": _label(kind, prev_key), "totals": _totals(conn, prev_start, prev_end)}
            counts = {
                "artists": {r["id"]: r["plays"] for r in _artist_rows(conn, prev_start, prev_end, limit=None)},
                "albums": {r["id"]: r["plays"] for r in _album_rows(conn, prev_start, prev_end, limit=None)},
                "tracks": {r["id"]: r["plays"] for r in _track_rows(conn, prev_start, prev_end, limit=None)},
            }
            data["new_artists"] = _artist_rows(conn, start, end, limit=None, only_new_since=True)
            data["discovery"] = data["new_artists"][0] if data["new_artists"] else None
        for kind_name, rows in data["top"].items():
            for row in rows:
                row["previous_plays"] = counts[kind_name].get(row["id"])
        return data


def recap_index(tz) -> dict:
    zone = _zone(tz)
    with closing(stats_db.connect()) as conn:
        moments = [row[0] for row in conn.execute("SELECT listened_at FROM plays ORDER BY listened_at")]
    if not moments:
        return {"months": [], "years": [], "latest_complete": None}
    months, years = Counter(), Counter()
    for moment in moments:
        local = datetime.fromtimestamp(moment, zone)
        months[f"{local.year:04d}-{local.month:02d}"] += 1
        years[f"{local.year:04d}"] += 1
    first = datetime.fromtimestamp(moments[0], zone)
    now = datetime.fromtimestamp(time.time(), zone)
    this_month, this_year = f"{now.year:04d}-{now.month:02d}", f"{now.year:04d}"
    first_month, first_year = f"{first.year:04d}-{first.month:02d}", f"{first.year:04d}"

    def entries(counter, period, current, first_key, partial):
        return [{
            "key": key, "label": _label(period, key), "plays": counter[key],
            "partial": key == first_key and partial, "so_far": key >= current,
        } for key in sorted(counter, reverse=True)]

    month_rows = entries(months, "month", this_month, first_month, first.day > 1)
    year_rows = entries(years, "year", this_year, first_year, (first.month, first.day) != (1, 1))
    complete = next((row["key"] for row in month_rows if not row["so_far"]), None)
    return {"months": month_rows, "years": year_rows, "latest_complete": complete}


_ENTITY_FILTERS = {
    "artist": "p.track_id IN (SELECT track_id FROM track_artists WHERE artist_id = ?)",
    "album": "p.album_id = ?",
    "track": "p.track_id = ?",
}


def entity(kind, entity_id, tz):
    if kind not in _ENTITY_FILTERS:
        raise BadPeriod("Unknown kind")
    zone = _zone(tz)
    with closing(stats_db.connect()) as conn:
        if kind == "artist":
            row = conn.execute("SELECT name, '' artist, picture_url image, '' deezer_track_id FROM artists WHERE id = ?", (entity_id,)).fetchone()
        elif kind == "album":
            row = conn.execute("SELECT title name, album_artist artist, cover_url image, '' deezer_track_id FROM albums WHERE id = ?", (entity_id,)).fetchone()
        else:
            row = conn.execute("SELECT title name, artist_display artist, cover_url image, deezer_track_id FROM tracks WHERE id = ?", (entity_id,)).fetchone()
        if row is None:
            return None
        where = _ENTITY_FILTERS[kind]
        summary = conn.execute(
            f"SELECT COUNT(*) plays, COALESCE(SUM({_SECONDS}), 0) seconds, MIN(p.listened_at) first_play, MAX(p.listened_at) last_play"
            f" FROM plays p JOIN tracks t ON t.id = p.track_id WHERE {where}", (entity_id,),
        ).fetchone()
        months = Counter()
        for (moment,) in conn.execute(f"SELECT p.listened_at FROM plays p WHERE {where}", (entity_id,)):
            local = datetime.fromtimestamp(moment, zone)
            months[f"{local.year:04d}-{local.month:02d}"] += 1
        top_tracks = []
        if kind != "track":
            top_tracks = [dict(r) for r in conn.execute(
                "SELECT t.id, t.title, t.artist_display artist, t.deezer_track_id, COUNT(*) plays FROM plays p JOIN tracks t ON t.id = p.track_id"
                f" WHERE {where} GROUP BY t.id ORDER BY plays DESC, t.title LIMIT {TOP_SIZE}", (entity_id,),
            )]
        return {
            "kind": kind, "id": entity_id, "name": row["name"], "artist": row["artist"], "image": row["image"] or "",
            "deezer_track_id": row["deezer_track_id"] or "", "plays": summary["plays"], "seconds": int(round(summary["seconds"])),
            "first_play": summary["first_play"], "last_play": summary["last_play"],
            "by_month": [{"key": key, "plays": months[key]} for key in sorted(months)],
            "top_tracks": top_tracks,
        }


def search_plays(q, page, per_page=50) -> dict:
    needle = stats_db.fold(q or "").strip()
    page = max(1, int(page or 1))
    with closing(stats_db.connect()) as conn:
        conn.create_function("fold", 1, stats_db.fold, deterministic=True)
        where, args = "1=1", ()
        if needle:
            where = "instr(fold(t.title || ' ' || t.artist_display || ' ' || COALESCE(al.title, '')), ?) > 0"
            args = (needle,)
        joins = "FROM plays p JOIN tracks t ON t.id = p.track_id LEFT JOIN albums al ON al.id = p.album_id"
        total = conn.execute(f"SELECT COUNT(*) {joins} WHERE {where}", args).fetchone()[0]
        rows = conn.execute(
            f"SELECT p.id, p.listened_at, p.source, p.track_id, t.title, t.artist_display artist, al.title album,"
            f" {_SECONDS} duration {joins} WHERE {where} ORDER BY p.listened_at DESC, p.id DESC LIMIT ? OFFSET ?",
            (*args, per_page, (page - 1) * per_page),
        ).fetchall()
    return {"plays": [dict(r) for r in rows], "total": total, "page": page, "pages": max(1, math.ceil(total / per_page))}
