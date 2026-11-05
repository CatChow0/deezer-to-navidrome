import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile as sf
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TIT2, TPE1, TXXX

from core import metadata_fix as fix, mixes_db

NOW = 1_800_000_000
DAY = 86400


def noise(seconds=12, rate=22050):
    return np.random.default_rng(3).normal(0, 0.2, int(seconds * rate)).astype("float32")


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for suffix in ("", "-wal", "-shm"):
            Path(f"{mixes_db.db_path()}{suffix}").unlink(missing_ok=True)
        self.conn = mixes_db.connect()
        self.addCleanup(self.conn.close)

    def flac(self, name="a.flac", **tags):
        path = self.root / name
        sf.write(path, noise(), 22050)
        audio = FLAC(path)
        for key, value in {"artist": "Vald", "title": "Song", "album": "Album", "deezer_track_id": "5", **tags}.items():
            audio[key] = value
        picture = Picture()
        picture.mime, picture.type, picture.data = "image/jpeg", 3, b"cover"
        audio.add_picture(picture)
        audio.save()
        return path

    def mp3(self, name="a.mp3"):
        path = self.root / name
        sf.write(path, noise(), 22050, format="MP3")
        tags = ID3()
        tags.add(TPE1(encoding=3, text="Vald"))
        tags.add(TIT2(encoding=3, text="Song"))
        tags.add(TXXX(encoding=3, desc="DEEZER_TRACK_ID", text="5"))
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="c", data=b"cover"))
        tags.save(path, v2_version=3)
        return path

    def entry(self, path):
        return {"path": str(path), "mtime_ns": Path(path).stat().st_mtime_ns,
                "tag_artist": "Vald", "tag_title": "Song", "tag_album": "Album"}


class Writing(Base):
    def test_adds_tempo_and_genre_to_a_flac(self):
        path = self.flac()
        self.assertTrue(fix.write_tags(path, 121.6, "Rap"))
        audio = FLAC(path)
        self.assertEqual(audio["bpm"], ["122"])
        self.assertEqual(audio["genre"], ["Rap"])

    def test_flac_keeps_every_other_tag_its_cover_and_its_audio(self):
        path = self.flac()
        before = FLAC(path)
        md5, tags = before.info.md5_signature, {k: before[k] for k in before.keys()}
        fix.write_tags(path, 120, "Rap")
        after = FLAC(path)
        self.assertEqual(after.info.md5_signature, md5)
        self.assertEqual(after.pictures[0].data, b"cover")
        for key, value in tags.items():
            self.assertEqual(after[key], value)
        self.assertTrue(np.array_equal(sf.read(path)[0], sf.read(path)[0]))

    def test_mp3_gets_the_tags_and_keeps_the_rest(self):
        path = self.mp3()
        fix.write_tags(path, 90, "Rap")
        tags = ID3(path)
        self.assertEqual(str(tags["TBPM"]), "90")
        self.assertEqual(str(tags["TCON"]), "Rap")
        self.assertEqual(str(tags["TPE1"]), "Vald")
        self.assertEqual(str(tags["TXXX:DEEZER_TRACK_ID"]), "5")
        self.assertEqual(tags["APIC:c"].data, b"cover")

    def test_read_back_what_was_written(self):
        path = self.flac()
        fix.write_tags(path, 120, "Rap")
        self.assertEqual(fix.read_tags(path), (120.0, "Rap"))

    def test_format_without_tags_is_skipped_untouched(self):
        path = self.root / "a.wav"
        sf.write(path, noise(), 22050)
        before = path.read_bytes()
        self.assertFalse(fix.write_tags(path, 120, "Rap"))
        self.assertEqual(path.read_bytes(), before)

    def test_no_temporary_file_is_left(self):
        path = self.flac()
        fix.write_tags(path, 120, "Rap")
        self.assertEqual([p.name for p in self.root.iterdir()], ["a.flac"])


class WritingFails(Base):
    def assertUntouched(self, path, before):
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual([p.name for p in self.root.iterdir()], [path.name])

    def test_audio_that_differs_refuses_and_leaves_the_original(self):
        path = self.flac()
        before = path.read_bytes()
        with mock.patch("core.metadata_fix._same_audio", return_value=False):
            with self.assertRaises(fix.WriteRefused):
                fix.write_tags(path, 120, "Rap")
        self.assertUntouched(path, before)

    def test_lost_tags_refuse_and_leave_the_original(self):
        path = self.flac()
        before = path.read_bytes()
        with mock.patch("core.metadata_fix._kept_all_tags", return_value=False):
            with self.assertRaises(fix.WriteRefused):
                fix.write_tags(path, 120, "Rap")
        self.assertUntouched(path, before)

    def test_corrupt_save_refuses_and_leaves_the_original(self):
        path = self.flac()
        before = path.read_bytes()
        with mock.patch("mutagen.flac.FLAC.save", side_effect=RuntimeError("boom")):
            with self.assertRaises(fix.WriteRefused):
                fix.write_tags(path, 120, "Rap")
        self.assertUntouched(path, before)

    def test_read_only_folder_is_an_error_not_a_crash(self):
        path = self.flac()
        with mock.patch("shutil.copy2", side_effect=PermissionError("read-only")):
            with self.assertRaises(OSError):
                fix.write_tags(path, 120, "Rap")

    def test_a_truly_different_audio_is_detected(self):
        path, other = self.flac(), self.root / "b.flac"
        sf.write(other, noise() * 0.5, 22050)
        self.assertFalse(fix._same_audio(path, other))

    def test_a_truly_lost_tag_is_detected(self):
        path, other = self.flac(), self.flac("b.flac")
        audio = FLAC(other)
        del audio["deezer_track_id"]
        audio.save()
        self.assertFalse(fix._kept_all_tags(path, other, {}))

    def test_a_lost_cover_is_detected(self):
        path, other = self.flac(), self.flac("b.flac")
        audio = FLAC(other)
        audio.clear_pictures()
        audio.save()
        self.assertFalse(fix._kept_all_tags(path, other, {}))


class Reading(Base):
    def test_junk_counts_as_missing(self):
        self.assertEqual(fix.read_tags(self.flac(genre="<unknown>", bpm="fast")), (None, None))
        self.assertEqual(fix.read_tags(self.flac("b.flac", genre="125", bpm="0")), (None, None))

    def test_unreadable_file(self):
        path = self.root / "x.flac"
        path.write_bytes(b"not audio")
        self.assertEqual(fix.read_tags(path), (None, None))
        self.assertEqual(fix.read_tags(self.root / "gone.flac"), (None, None))


class FixFile(Base):
    def fix(self, path, tempo=128.0, genre="Rap", write=fix.write_tags):
        api = mock.Mock()
        with mock.patch("core.audio_tempo.file_tempo", return_value=tempo) as measure, \
                mock.patch("core.metadata_fix.lookup_genre", return_value=genre) as look:
            result = fix.fix_file(self.conn, self.entry(path), NOW, api, write)
        self.measure, self.look = measure, look
        return result

    def test_fills_what_is_missing(self):
        path = self.flac()
        self.assertTrue(self.fix(path)["written"])
        self.assertEqual(fix.read_tags(path), (128.0, "Rap"))
        self.assertEqual(fix.features_map(self.conn)[str(path)], (128.0, "Rap"))

    def test_a_value_in_the_file_is_never_replaced(self):
        path = self.flac(genre="Metal", bpm="77")
        self.assertFalse(self.fix(path, tempo=128.0, genre="Rap")["written"])
        self.assertEqual(fix.read_tags(path), (77.0, "Metal"))
        self.assertEqual(fix.features_map(self.conn)[str(path)], (77.0, "Metal"))

    def test_a_file_already_complete_is_not_rewritten(self):
        path = self.flac(genre="Metal", bpm="77")
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        self.fix(path)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_a_tempo_in_the_tags_is_not_measured_again(self):
        self.fix(self.flac(bpm="77"))
        self.measure.assert_not_called()

    def test_a_genre_in_the_tags_is_not_looked_up(self):
        self.fix(self.flac(genre="Metal"))
        self.look.assert_not_called()

    def test_only_the_missing_value_is_added(self):
        path = self.flac(genre="Metal")
        self.fix(path, tempo=128.0)
        self.assertEqual(fix.read_tags(path), (128.0, "Metal"))

    def test_nothing_found_writes_nothing(self):
        path = self.flac()
        before = path.read_bytes()
        result = self.fix(path, tempo=None, genre=None)
        self.assertFalse(result["written"])
        self.assertEqual(path.read_bytes(), before)

    def test_a_failed_write_still_counts_for_the_mixes(self):
        path = self.flac()
        result = self.fix(path, write=mock.Mock(side_effect=PermissionError("read-only")))
        self.assertIn("read-only", result["error"])
        self.assertEqual(fix.features_map(self.conn)[str(path)], (128.0, "Rap"))
        self.conn.commit()
        self.assertEqual(fix.status(self.conn, [self.entry(path)])["write_errors"], 1)


class Once(Base):
    """A file is measured once: the point of keeping results."""

    def test_not_pending_after_being_done_even_before_the_index_refreshes(self):
        path = self.flac()
        stale_entry = self.entry(path)
        with mock.patch("core.audio_tempo.file_tempo", return_value=128.0), \
                mock.patch("core.metadata_fix.lookup_genre", return_value="Rap"):
            fix.fix_file(self.conn, stale_entry, NOW)
        self.assertNotEqual(stale_entry["mtime_ns"], path.stat().st_mtime_ns)   # it was written
        self.assertEqual(fix.pending(self.conn, [stale_entry], NOW), [])

    def test_not_pending_after_the_index_refreshes(self):
        path = self.flac()
        with mock.patch("core.audio_tempo.file_tempo", return_value=128.0), \
                mock.patch("core.metadata_fix.lookup_genre", return_value="Rap"):
            fix.fix_file(self.conn, self.entry(path), NOW)
        self.assertEqual(fix.pending(self.conn, [self.entry(path)], NOW), [])

    def test_a_file_changed_later_is_looked_at_again_without_measuring(self):
        path = self.flac()
        with mock.patch("core.audio_tempo.file_tempo", return_value=128.0) as measure, \
                mock.patch("core.metadata_fix.lookup_genre", return_value="Rap"):
            fix.fix_file(self.conn, self.entry(path), NOW)
            audio = FLAC(path)
            audio["title"] = "Renamed"
            audio.save()
            self.assertEqual(len(fix.pending(self.conn, [self.entry(path)], NOW)), 1)
            fix.fix_file(self.conn, self.entry(path), NOW)
        measure.assert_called_once()

    def test_a_lost_database_does_not_measure_again(self):
        path = self.flac()
        with mock.patch("core.audio_tempo.file_tempo", return_value=128.0) as measure, \
                mock.patch("core.metadata_fix.lookup_genre", return_value="Rap") as look:
            fix.fix_file(self.conn, self.entry(path), NOW)
            self.conn.execute("DELETE FROM track_features")
            fix.fix_file(self.conn, self.entry(path), NOW)
        measure.assert_called_once()
        look.assert_called_once()

    def test_a_read_only_file_is_not_measured_again(self):
        path = self.flac()
        with mock.patch("core.audio_tempo.file_tempo", return_value=128.0) as measure, \
                mock.patch("core.metadata_fix.lookup_genre", return_value="Rap"):
            for _ in range(2):
                fix.fix_file(self.conn, self.entry(path), NOW, write=mock.Mock(side_effect=PermissionError("ro")))
        measure.assert_called_once()

    def test_a_moved_file_keeps_its_result(self):
        path = self.flac()
        with mock.patch("core.audio_tempo.file_tempo", return_value=128.0), \
                mock.patch("core.metadata_fix.lookup_genre", return_value="Rap"):
            fix.fix_file(self.conn, self.entry(path), NOW)
        new = self.root / "moved.flac"
        path.rename(new)
        fix.move_file(self.conn, path, new)
        self.assertEqual(fix.features_map(self.conn)[str(new)], (128.0, "Rap"))
        self.assertEqual(fix.pending(self.conn, [self.entry(new)], NOW), [])

    def test_a_genre_not_found_is_tried_again_after_a_month_only(self):
        path = self.flac()
        with mock.patch("core.audio_tempo.file_tempo", return_value=128.0), \
                mock.patch("core.metadata_fix.lookup_genre", return_value=None):
            fix.fix_file(self.conn, self.entry(path), NOW)
        e = {**self.entry(path)}
        self.assertEqual(fix.pending(self.conn, [e], NOW + DAY), [])
        self.assertEqual(len(fix.pending(self.conn, [e], NOW + 31 * DAY)), 1)

    def test_run_can_stop_and_resume(self):
        paths = [self.flac(f"{i}.flac") for i in range(4)]
        entries = [self.entry(p) for p in paths]
        seen = []
        with mock.patch("core.audio_tempo.file_tempo", return_value=None), \
                mock.patch("core.metadata_fix.lookup_genre", return_value=None):
            report = fix.run(self.conn, entries, should_stop=lambda: seen.append(1) or len(seen) > 2)
        self.assertEqual(report["done"], 2)
        self.assertEqual(len(fix.pending(self.conn, entries)), 2)


class DeezerLanguage(unittest.TestCase):
    def test_public_api_asks_for_english_names(self):
        from core import deezer
        response = mock.Mock()
        response.json.return_value = {"data": []}
        with mock.patch("core.deezer.requests.get", return_value=response) as get:
            deezer._public_api("/genre")
        self.assertEqual(get.call_args.kwargs["headers"]["Accept-Language"], "en")


class GenreLookup(Base):
    def api(self, albums=(), tracks=(), genre="Rap/Hip Hop"):
        calls = []

        def call(path, params=None):
            calls.append(path)
            if path == "/search/album":
                return {"data": list(albums)}
            if path == "/search/track":
                return {"data": list(tracks)}
            return {"genres": {"data": [{"name": genre}] if genre else []}}

        call.calls = calls
        return call

    def album(self, artist="Vald", title="Album", id=7):
        return {"id": id, "title": title, "artist": {"name": artist}}

    def track(self, artist="Vald", title="Song", album_id=8):
        return {"title": title, "artist": {"name": artist}, "album": {"id": album_id}}

    def look(self, api, artist="Vald", title="Song", album="Album", now=NOW):
        return fix.lookup_genre(self.conn, artist, title, album, now, api)

    def test_finds_it_through_the_album(self):
        api = self.api(albums=[self.album()])
        self.assertEqual(self.look(api), "Rap/Hip Hop")
        self.assertIn("/album/7", api.calls)

    def test_a_wrong_album_is_not_accepted(self):
        api = self.api(albums=[self.album(artist="Someone else"), self.album(title="Other record")])
        self.assertIsNone(self.look(api))
        self.assertNotIn("/album/7", api.calls)

    def test_falls_back_on_the_track(self):
        api = self.api(tracks=[self.track()])
        self.assertEqual(self.look(api), "Rap/Hip Hop")
        self.assertIn("/album/8", api.calls)

    def test_a_wrong_track_is_not_accepted(self):
        api = self.api(tracks=[self.track(artist="Someone else"), self.track(title="Nothing alike")])
        self.assertIsNone(self.look(api))

    def test_one_search_per_album(self):
        api = self.api(albums=[self.album()])
        self.look(api, title="One")
        count = len(api.calls)
        self.assertEqual(self.look(api, title="Two"), "Rap/Hip Hop")
        self.assertEqual(len(api.calls), count)

    def test_unknown_artist_is_not_searched(self):
        api = self.api(albums=[self.album()])
        self.assertIsNone(self.look(api, artist="[Unknown Artist]"))
        self.assertEqual(api.calls, [])

    def test_not_found_is_remembered_for_a_month(self):
        api = self.api()
        self.look(api)
        count = len(api.calls)
        self.look(api, now=NOW + DAY)
        self.assertEqual(len(api.calls), count)
        self.look(api, now=NOW + 31 * DAY)
        self.assertGreater(len(api.calls), count)

    def test_a_deezer_failure_is_not_remembered(self):
        broken = mock.Mock(side_effect=RuntimeError("down"))
        self.assertIsNone(self.look(broken))
        self.assertEqual(self.look(self.api(albums=[self.album()])), "Rap/Hip Hop")

    def test_album_without_a_genre(self):
        self.assertIsNone(self.look(self.api(albums=[self.album()], genre=None)))


if __name__ == "__main__":
    unittest.main()
