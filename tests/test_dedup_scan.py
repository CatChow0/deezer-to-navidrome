"""A duplicate scan reads the whole library: one at a time, started by any account
(the accounts of this app are trusted ones), and asking again follows the one running."""
import threading
import time
import unittest
from unittest import mock

from routes import dedup as dedup_routes
from tests.test_users import PASSWORD, Base


class Scan(Base):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        super().setUp()
        self.client = self.app.test_client()
        self.assertEqual(302, self.client.post("/login", data={"username": "alice", "password": PASSWORD}).status_code)
        self.addCleanup(self.wait_until_over)

    def wait_until_over(self):
        deadline = time.monotonic() + 5
        while dedup_routes._scan_task is not None and time.monotonic() < deadline:
            time.sleep(0.01)

    def start(self):
        response = self.client.post("/dedup/start")
        self.assertEqual(200, response.status_code)
        return response.get_json()["task_id"]

    def test_an_account_that_is_not_an_admin_may_start_a_scan(self):
        with mock.patch.object(dedup_routes, "run_dedup_analysis", return_value={"group_count": 0}):
            self.assertTrue(self.start())

    def test_a_second_scan_asked_while_one_runs_follows_it(self):
        release, runs = threading.Event(), []

        def slow(progress_cb=None):
            runs.append(1)
            release.wait(5)
            return {"group_count": 0}

        with mock.patch.object(dedup_routes, "run_dedup_analysis", side_effect=slow):
            first = self.start()
            self.assertEqual(first, self.start())
            self.assertEqual(first, self.start())
            release.set()
            self.wait_until_over()
            second = self.start()
            self.wait_until_over()
        self.assertNotEqual(first, second)
        self.assertEqual(2, len(runs))

    def test_another_account_is_told_to_wait_for_a_scan_it_cannot_see(self):
        release = threading.Event()

        def slow(progress_cb=None):
            release.wait(5)
            return {"group_count": 0}

        with mock.patch.object(dedup_routes, "run_dedup_analysis", side_effect=slow):
            first = self.start()
            bob = self.app.test_client()
            self.assertEqual(302, bob.post("/login", data={"username": "bob", "password": PASSWORD}).status_code)
            refused = bob.post("/dedup/start")
            self.assertEqual(409, refused.status_code)
            self.assertIn("already running", refused.get_json()["error"])
            admin = self.app.test_client()
            self.assertEqual(302, admin.post("/login", data={"username": "admin", "password": PASSWORD}).status_code)
            self.assertEqual(first, admin.post("/dedup/start").get_json()["task_id"])  # an Admin sees every task
            release.set()
            self.wait_until_over()

    def test_a_scan_that_fails_lets_the_next_one_start(self):
        with mock.patch.object(dedup_routes, "run_dedup_analysis", side_effect=RuntimeError("disk")) as run:
            first = self.start()
            self.wait_until_over()
            self.assertIsNone(dedup_routes._scan_task)
            self.assertNotEqual(first, self.start())
            self.wait_until_over()
        self.assertEqual(2, run.call_count)


if __name__ == "__main__":
    unittest.main()
