"""The automatic scans: kept on schedule across restarts, never run twice at
once, and a failing pass never stops the scheduler."""
import threading
import time
import unittest
from unittest import mock

from core import scheduler


def playlist(pid, minutes=60):
    return {"id": pid, "auto_scan_enabled": True, "auto_scan_interval_minutes": minutes}


class Schedule(unittest.TestCase):
    def setUp(self):
        scheduler._state.clear()
        scheduler._running.clear()
        scheduler._last_runs_file().unlink(missing_ok=True)
        self.addCleanup(scheduler._state.clear)
        self.addCleanup(lambda: scheduler._last_runs_file().unlink(missing_ok=True))

    def test_a_scan_known_from_before_a_restart_keeps_its_time(self):
        now = int(time.time())
        scheduler._save_last_run("1", now - 3600 * 23)
        scheduler._save_last_run("2", now - 3600 * 30)
        scheduler._sync_state_from_playlists([playlist("1", 24 * 60), playlist("2", 24 * 60), playlist("3", 24 * 60)])
        state = scheduler.get_status()
        self.assertAlmostEqual(now + 3600, state["1"]["next_run_at"], delta=5)
        self.assertAlmostEqual(now, state["2"]["next_run_at"], delta=5)
        self.assertAlmostEqual(now + 24 * 3600, state["3"]["next_run_at"], delta=5)

    def test_a_playlist_being_scanned_is_not_scanned_again(self):
        scheduler._state["1"] = {"next_run_at": 0, "last_run_at": None}
        scheduler._running.add("1")
        with mock.patch("core.deezer.load_playlists", return_value=[playlist("1")]), \
                mock.patch("core.stats_enrich.start_background_batch"), \
                mock.patch.object(scheduler, "_refresh_releases_if_stale"), \
                mock.patch.object(scheduler, "_last_mix_check", time.time()), \
                mock.patch.object(scheduler, "_run_playlist") as run:
            scheduler._one_pass(threading.Event())
        run.assert_not_called()

    def test_a_scan_that_fails_still_moves_its_next_time(self):
        scheduler._state["1"] = {"next_run_at": 0, "last_run_at": None}
        with mock.patch("core.deezer.load_playlists", return_value=[playlist("1")]), \
                mock.patch("core.stats_enrich.start_background_batch"), \
                mock.patch("core.config.load_config", return_value={}), \
                mock.patch.object(scheduler, "_refresh_releases_if_stale"), \
                mock.patch.object(scheduler, "_last_mix_check", time.time()), \
                mock.patch.object(scheduler, "_run_playlist", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                scheduler._one_pass(threading.Event())
        self.assertGreater(scheduler.get_status()["1"]["next_run_at"], time.time())
        self.assertEqual(set(), scheduler._running)

    def test_the_loop_survives_a_failing_pass_and_stops_on_its_own_event(self):
        stop = threading.Event()
        calls = []

        def failing(event):
            calls.append(event)
            stop.set()
            raise RuntimeError("boom")

        with mock.patch.object(scheduler, "_one_pass", side_effect=failing), \
                mock.patch.object(stop, "wait", side_effect=[False, True]):
            scheduler._scheduler_loop(stop)
        self.assertEqual([stop], calls)


if __name__ == "__main__":
    unittest.main()
