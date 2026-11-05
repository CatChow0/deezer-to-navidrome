import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from core import config, metadata_fix as fix, mix_builder as mb, mixes_db, stats_db
from core.config import TaskCancelled, cancel_requested, create_task, push_task_event, request_cancel


class Tasks(unittest.TestCase):
    def test_a_cancellable_task_stops_at_its_next_progress(self):
        task = create_task("T", cancellable=True)
        push_task_event(task, "working")
        self.assertTrue(request_cancel(task))
        with self.assertRaises(TaskCancelled):
            push_task_event(task, "more work")

    def test_a_task_that_cannot_stop_refuses(self):
        task = create_task("T")
        self.assertFalse(request_cancel(task))
        push_task_event(task, "still working")

    def test_a_finished_task_refuses(self):
        task = create_task("T", cancellable=True)
        push_task_event(task, "done", done=True)
        self.assertFalse(request_cancel(task))

    def test_an_unknown_task_refuses(self):
        self.assertFalse(request_cancel("nope"))

    def test_the_error_of_a_cancelled_task_is_a_cancellation(self):
        task = create_task("T", cancellable=True)
        request_cancel(task)
        push_task_event(task, "Rebuild failed: cancelled", stage="error", done=True, error=True)
        item = config.TASKS[task]
        self.assertTrue(item["cancelled"])
        self.assertFalse(item["error"])
        self.assertTrue(item["done"])
        self.assertTrue(item["events"][-1]["cancelled"])
        self.assertFalse(item["events"][-1]["error"])

    def test_a_task_finishing_before_it_stops_stays_a_success(self):
        task = create_task("T", cancellable=True)
        request_cancel(task)
        push_task_event(task, "All done", done=True)
        self.assertFalse(config.TASKS[task]["cancelled"])

    def test_the_stopping_message_does_not_raise(self):
        task = create_task("T", cancellable=True)
        self.assertTrue(request_cancel(task))
        self.assertEqual(config.TASKS[task]["stage"], "stopping")
        self.assertTrue(cancel_requested(task))

    def test_a_quiet_push_can_report_without_stopping(self):
        task = create_task("T", cancellable=True)
        request_cancel(task)
        push_task_event(task, "finishing a file", check_cancel=False)

    def test_the_page_knows_at_once_that_it_can_stop(self):
        task = create_task("T", cancellable=True)
        self.assertEqual(len(config.TASKS[task]["events"]), 1)
        self.assertEqual(config.TASKS[create_task("T")]["events"], [])

    def test_summary_tells_the_page(self):
        task = create_task("T", cancellable=True)
        summary = config.task_summary(config.TASKS[task])
        self.assertTrue(summary["cancellable"])
        self.assertFalse(summary["cancelled"])


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.app.test_client()

    def test_cancel(self):
        task = create_task("T", cancellable=True)
        self.assertEqual(self.client.post(f"/api/tasks/{task}/cancel").status_code, 200)
        self.assertTrue(cancel_requested(task))

    def test_cancel_refused(self):
        self.assertEqual(self.client.post("/api/tasks/nope/cancel").status_code, 404)
        task = create_task("T")
        self.assertEqual(self.client.post(f"/api/tasks/{task}/cancel").status_code, 409)

    def test_stream_events_carry_the_clock_and_what_the_page_needs(self):
        task = create_task("T", cancellable=True)
        push_task_event(task, "working")
        push_task_event(task, "done", done=True)
        body = self.client.get(f"/tasks/{task}/stream").data.decode()
        self.assertIn('"server_now"', body)
        self.assertIn('"created_at"', body)
        self.assertIn('"cancellable": true', body)

    def test_every_long_task_can_be_cancelled(self):
        from pathlib import Path as P
        root = P(__file__).resolve().parent.parent
        for path, marker in (("routes/cache.py", "Full library rebuild"), ("routes/cache.py", "Library refresh"),
                             ("routes/dedup.py", "Duplicate scan"), ("routes/system.py", "Repair downloads"),
                             ("routes/account.py", "create_task(title"), ("routes/mixes.py", "Fix missing metadata"),
                             ("routes/mixes.py", "Undo metadata fix"), ("core/mix_builder.py", "create_task(title"),
                             ("core/stats_import.py", "create_task(title")):
            text = (root / path).read_text(encoding="utf-8")
            line = next(l for l in text.splitlines() if "create_task" in l and marker in l)
            self.assertIn("cancellable=True", line, marker)


class FixCancel(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for suffix in ("", "-wal", "-shm"):
            Path(f"{mixes_db.db_path()}{suffix}").unlink(missing_ok=True)
        self.conn = mixes_db.connect()
        self.addCleanup(self.conn.close)

    def wait(self):
        for _ in range(200):
            if not fix.is_running():
                return
            time.sleep(0.05)
        self.fail("Still running")

    def entries(self, count=30):
        items = []
        for i in range(count):
            path = self.root / f"{i}.wav"
            path.write_bytes(b"x")
            items.append({"path": str(path), "mtime_ns": 1})
        return items

    def run_and_cancel(self, entries):
        task = create_task("Fix", cancellable=True)
        started = threading.Event()

        def slow(path):
            started.set()
            time.sleep(0.05)
            return 100.0

        with mock.patch("core.audio_tempo.file_tempo", side_effect=slow), \
                mock.patch("core.metadata_fix.lookup_genre", return_value=None), \
                mock.patch("core.metadata_fix.available", return_value=True), \
                mock.patch("core.metadata_fix.workers_setting", return_value=2), \
                mock.patch("core.metadata_fix._refresh_library"):
            fix.start_background(lambda: entries, task_id=task)
            started.wait(5)
            request_cancel(task)
            self.wait()
        return task

    def test_it_stops_early_and_says_so(self):
        entries = self.entries()
        task = self.run_and_cancel(entries)
        item = config.TASKS[task]
        self.assertTrue(item["done"])
        self.assertTrue(item["cancelled"])
        self.assertFalse(item["error"])
        self.assertIn("Cancelled", item["message"])
        self.assertGreater(len(fix.pending(self.conn, entries)), 0)

    def test_it_does_not_come_back_by_itself(self):
        entries = self.entries()
        self.run_and_cancel(entries)
        self.assertTrue(fix.paused(self.conn))
        with mock.patch("core.mix_builder.library_entries", return_value=entries), \
                mock.patch("core.metadata_fix.start_background") as start:
            mixes_db.set_meta(self.conn, "metadata_fix_on", True)
            mb.tick(1_800_000_000)
            mb.save_settings(self.conn, {"mix_mode": "daily"})
            mb.tick(1_800_000_000)
        start.assert_not_called()

    def test_automatic_passes_show_in_activity(self):
        entries = self.entries(1)
        before = set(config.TASKS)
        with mock.patch("core.audio_tempo.file_tempo", return_value=100.0), \
                mock.patch("core.metadata_fix.lookup_genre", return_value=None), \
                mock.patch("core.metadata_fix.available", return_value=True), \
                mock.patch("core.metadata_fix._refresh_library"):
            fix.start_background(lambda: entries)
            self.wait()
        new = [config.TASKS[t] for t in set(config.TASKS) - before]
        self.assertEqual(len(new), 1)
        self.assertTrue(new[0]["cancellable"])
        self.assertTrue(new[0]["visible"])

    def test_nothing_to_do_makes_no_noise(self):
        before = set(config.TASKS)
        with mock.patch("core.metadata_fix.available", return_value=True):
            fix.start_background(lambda: [])
            self.wait()
        self.assertEqual(set(config.TASKS) - before, set())

    def test_an_undo_can_be_cancelled_and_stays_resumable(self):
        for i in range(3):
            self.conn.execute("INSERT INTO track_features(path, mtime_ns, analyzed_at, added_bpm) VALUES (?,?,?,?)",
                              (str(self.root / f"gone{i}.flac"), 1, 1, "120"))
        self.conn.commit()
        report = fix.undo(self.conn, should_stop=lambda: True)
        self.assertEqual(report["undone"] + report["errors"], 0)
        self.assertEqual(fix.status(self.conn, [])["can_undo"], 3)


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        for suffix in ("", "-wal", "-shm"):
            Path(f"{mixes_db.db_path()}{suffix}").unlink(missing_ok=True)
        patches = [mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}),
                   mock.patch("core.metadata_fix.start_background"),
                   mock.patch("core.mix_builder.library_entries", return_value=[])]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.client = self.app.test_client()
        self.conn = mixes_db.connect()
        self.addCleanup(self.conn.close)

    def test_the_button_resumes_after_a_cancel(self):
        mixes_db.set_meta(self.conn, "metadata_fix_paused", True)
        self.client.post("/api/metadata/fix", json={})
        self.assertFalse(fix.paused(self.conn))

    def test_turning_a_mix_on_resumes_after_a_cancel(self):
        mixes_db.set_meta(self.conn, "metadata_fix_paused", True)
        self.client.post("/api/mixes/settings", json={"mix_mode": "daily"})
        self.assertFalse(fix.paused(self.conn))

    def test_while_running_the_button_follows_the_running_task(self):
        running = create_task("Fix", cancellable=True)
        with mock.patch("core.metadata_fix.is_running", return_value=True), \
                mock.patch("core.metadata_fix.current_task", return_value=running):
            data = self.client.post("/api/metadata/fix", json={}).get_json()
        self.assertEqual(data["task_id"], running)

    def test_status_says_it_is_paused(self):
        mixes_db.set_meta(self.conn, "metadata_fix_paused", True)
        self.assertTrue(self.client.get("/api/mixes").get_json()["analysis"]["paused"])


class MixCancel(unittest.TestCase):
    def test_a_cancelled_generation_waits_for_its_next_turn(self):
        for suffix in ("", "-wal", "-shm"):
            Path(f"{mixes_db.db_path()}{suffix}").unlink(missing_ok=True)
        with mock.patch("core.mix_builder.generate", side_effect=TaskCancelled()):
            task = mb.start_task(["daily"])
            for _ in range(100):
                if config.TASKS[task]["done"]:
                    break
                time.sleep(0.02)
        self.assertTrue(config.TASKS[task]["cancelled"] or config.TASKS[task]["done"])
        conn = mixes_db.connect()
        self.addCleanup(conn.close)
        self.assertGreater(mixes_db.get_meta(conn, "last_daily", 0), 0)


class RepairCancel(unittest.TestCase):
    def test_it_stops_before_the_next_file(self):
        from core import download_repair as repair
        for suffix in ("", "-wal", "-shm"):
            Path(f"{mixes_db.db_path()}{suffix}").unlink(missing_ok=True)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        for i in range(3):
            (root / f"{i}.flac").write_bytes(b"x")
        with mock.patch("core.deezer_dl.download_dir", return_value=root), \
                mock.patch("core.download_repair._read_tags", return_value={"deezer_id": "5"}) as read:
            summary = repair.repair_downloads(should_stop=lambda: read.call_count >= 1)
        self.assertTrue(summary["cancelled"])
        self.assertEqual(read.call_count, 1)


if __name__ == "__main__":
    unittest.main()
