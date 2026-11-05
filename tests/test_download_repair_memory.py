import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile as sf
from mutagen.flac import FLAC

from core import download_repair as repair, metadata_fix as fix, mixes_db

OLD = repair.BROKEN_SINCE - 86400 * 100
RECENT = repair.BROKEN_SINCE + 86400


def noise(seconds=12, rate=22050):
    return np.random.default_rng(5).normal(0, 0.2, int(seconds * rate)).astype("float32")


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for suffix in ("", "-wal", "-shm"):
            Path(f"{mixes_db.db_path()}{suffix}").unlink(missing_ok=True)
        self.conn = mixes_db.connect()
        self.addCleanup(self.conn.close)

    def audio(self, name, when, fmt=None):
        path = self.root / name
        sf.write(path, noise(), 22050, format=fmt)
        os.utime(path, (when, when))
        return path

    def fix(self, path):
        entry = {"path": str(path), "mtime_ns": path.stat().st_mtime_ns, "tag_artist": "A", "tag_title": "T"}
        with mock.patch("core.audio_tempo.file_tempo", return_value=128.0), \
                mock.patch("core.metadata_fix.lookup_genre", return_value="Rap"):
            fix.fix_file(self.conn, entry, 1_800_000_000, mock.Mock())

    def suspects(self):
        return repair.suspect_files(self.root, fix.original_mtimes(self.conn), fix.repair_checked(self.conn))


class Dates(Base):
    def test_an_old_file_stays_out_once_tagged(self):
        path = self.audio("old.flac", OLD)
        self.assertEqual(self.suspects(), [])
        self.fix(path)
        self.assertGreater(path.stat().st_mtime, repair.BROKEN_SINCE)   # tagging gave it a new date
        self.assertEqual(self.suspects(), [])

    def test_a_recent_file_stays_in_once_tagged(self):
        path = self.audio("recent.flac", RECENT)
        self.fix(path)
        self.assertEqual(self.suspects(), [path])

    def test_a_second_pass_keeps_the_first_date(self):
        path = self.audio("old.flac", OLD)
        self.fix(path)
        audio = FLAC(path)
        del audio["bpm"]
        audio.save()
        self.fix(path)
        self.assertEqual(fix.original_mtimes(self.conn)[str(path)], OLD)

    def test_a_moved_file_keeps_its_date_and_verdict(self):
        path = self.audio("old.flac", OLD)
        self.fix(path)
        fix.mark_repair_checked(self.conn, path)
        new = self.root / "new.flac"
        path.rename(new)
        fix.move_file(self.conn, path, new)
        self.assertEqual(fix.original_mtimes(self.conn)[str(new)], OLD)
        self.assertIn(str(new), fix.repair_checked(self.conn))

    def test_without_the_base_nothing_breaks_it_only_checks_more(self):
        path = self.audio("old.flac", OLD)
        self.fix(path)
        self.assertEqual(repair.suspect_files(self.root), [path])


class Verdicts(Base):
    def test_a_file_found_fine_is_not_downloaded_again(self):
        path = self.audio("recent.flac", RECENT)
        fix.mark_repair_checked(self.conn, path)
        self.assertEqual(self.suspects(), [])

    def test_the_verdict_survives_tagging(self):
        path = self.audio("recent.flac", RECENT)
        fix.mark_repair_checked(self.conn, path)
        self.fix(path)
        self.assertEqual(self.suspects(), [])

    def test_a_run_remembers_what_it_found_fine(self):
        path = self.audio("recent.flac", RECENT)
        with mock.patch("core.deezer_dl.download_dir", return_value=self.root), \
                mock.patch("core.download_repair._read_tags", return_value={"deezer_id": "5"}):
            first = repair.repair_downloads()
            second = repair.repair_downloads()
        self.assertEqual(first["checked"], 1)
        self.assertEqual(second["checked"], 0)
        self.assertIn(str(path), fix.repair_checked(self.conn))


class StillWorks(Base):
    """Repair recognises a file by the end of its bytes, where only audio is."""

    def test_window_is_the_same_after_tagging(self):
        for name, fmt in (("a.flac", None), ("a.mp3", "MP3")):
            path = self.root / name
            sf.write(path, noise(seconds=90), 22050, format=fmt)   # longer than the window, like a real track
            self.assertGreater(path.stat().st_size, repair.WINDOW * 2)
            before = repair._window(path.read_bytes())
            fix.write_tags(path, 120, "Rap")
            self.assertEqual(repair._window(path.read_bytes()), before, name)

    def test_the_repair_swap_takes_the_common_lock(self):
        import threading
        from core.utils import FILES_LOCK
        path = self.audio("a.flac", RECENT)
        done = threading.Event()
        FILES_LOCK.acquire()
        with mock.patch("core.deezer_dl._write_tags"):
            worker = threading.Thread(target=lambda: (repair._replace(path, b"new", {}, True), done.set()))
            worker.start()
            self.assertFalse(done.wait(1))
            FILES_LOCK.release()
            self.assertTrue(done.wait(5))
            worker.join()
        self.assertEqual(path.read_bytes(), b"new")


class FixWaits(unittest.TestCase):
    def test_a_pass_stops_while_a_repair_runs(self):
        stopped = fix.run(mock.Mock(**{"execute.return_value.fetchone.return_value": None}),
                          [{"path": "/x"}], should_stop=lambda: True)
        self.assertEqual(stopped["done"], 0)


if __name__ == "__main__":
    unittest.main()
