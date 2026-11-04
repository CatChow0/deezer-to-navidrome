"""Small source databases with the real Navidrome and Maloja table shapes."""
import json
import sqlite3


def make_navidrome(path, plays):
    """plays: dicts with ts, title, and optional artist, artists, album,
    album_artist, duration, genres, file."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE media_file (id TEXT PRIMARY KEY, title TEXT, artist TEXT, album TEXT, album_artist TEXT,
                                 duration REAL, tags TEXT, participants TEXT, missing INTEGER DEFAULT 0);
        CREATE TABLE scrobbles (id INTEGER PRIMARY KEY, media_file_id TEXT NOT NULL, user_id TEXT NOT NULL,
                                submission_time INTEGER NOT NULL);
    """)
    for play in plays:
        artists = play.get("artists") or [play.get("artist", "Artist")]
        file_id = play.get("file") or f"{artists[0]}/{play['title']}"
        tags = {"genre": [{"id": str(i), "value": g} for i, g in enumerate(play.get("genres", []))]}
        participants = {"artist": [{"id": str(i), "name": a} for i, a in enumerate(artists)]}
        conn.execute(
            "INSERT OR REPLACE INTO media_file(id, title, artist, album, album_artist, duration, tags, participants)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (file_id, play["title"], " • ".join(artists), play.get("album", "Album"),
             play.get("album_artist", artists[0]), play.get("duration", 200),
             json.dumps(tags), json.dumps(participants)),
        )
        conn.execute("INSERT INTO scrobbles(media_file_id, user_id, submission_time) VALUES (?, 'u', ?)", (file_id, play["ts"]))
    conn.commit()
    conn.close()


def make_maloja(path, plays):
    """plays: dicts with ts, title, and optional artist, artists, album, length."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE artists (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, name_normalized TEXT);
        CREATE TABLE albums (id INTEGER PRIMARY KEY AUTOINCREMENT, albtitle TEXT, albtitle_normalized TEXT);
        CREATE TABLE tracks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, title_normalized TEXT, length INTEGER, album_id INTEGER);
        CREATE TABLE albumartists (id INTEGER PRIMARY KEY, artist_id INTEGER, album_id INTEGER);
        CREATE TABLE trackartists (id INTEGER PRIMARY KEY, artist_id INTEGER, track_id INTEGER);
        CREATE TABLE scrobbles (timestamp INTEGER PRIMARY KEY, rawscrobble TEXT, origin TEXT, duration INTEGER, track_id INTEGER, extra TEXT);
    """)
    for play in plays:
        artists = play.get("artists") or [play.get("artist", "Artist")]
        artist_ids = []
        for name in artists:
            row = conn.execute("SELECT id FROM artists WHERE name=?", (name,)).fetchone()
            artist_ids.append(row[0] if row else conn.execute("INSERT INTO artists(name) VALUES (?)", (name,)).lastrowid)
        album_id = None
        if play.get("album"):
            album_id = conn.execute("INSERT INTO albums(albtitle) VALUES (?)", (play["album"],)).lastrowid
            conn.execute("INSERT INTO albumartists(artist_id, album_id) VALUES (?, ?)", (artist_ids[0], album_id))
        track_id = conn.execute(
            "INSERT INTO tracks(title, length, album_id) VALUES (?, ?, ?)", (play["title"], play.get("length"), album_id)
        ).lastrowid
        for artist_id in artist_ids:
            conn.execute("INSERT INTO trackartists(artist_id, track_id) VALUES (?, ?)", (artist_id, track_id))
        conn.execute("INSERT INTO scrobbles(timestamp, origin, track_id) VALUES (?, 'client:test', ?)", (play["ts"], track_id))
    conn.commit()
    conn.close()
