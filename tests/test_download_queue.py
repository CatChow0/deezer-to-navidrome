"""The download queue: one track asked twice is downloaded once, and every
caller hears when it is done."""
import unittest
from unittest import mock

from core import download_queue as dq


class Joining(unittest.TestCase):
    def setUp(self):
        self.queue = dq.DownloadQueue(workers=1)
        patcher = mock.patch.object(dq.DownloadQueue, "start")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_same_track_waiting_is_joined(self):
        heard = []
        first = self.queue.enqueue("d", "track", "1", on_done=lambda t, r, e: heard.append("first"))
        second = self.queue.enqueue("d", "track", "1", on_done=lambda t, r, e: heard.append("second"))
        self.assertIs(first, second)
        self.assertEqual(1, len(self.queue.queue))
        with mock.patch.object(self.queue, "_run", return_value={"path": "x"}):
            self.queue._run_task(self.queue.queue.pop(0))
        self.assertEqual(["first", "second"], heard)

    def test_another_folder_or_a_finished_one_is_a_new_download(self):
        first = self.queue.enqueue("d", "track", "1")
        self.assertIsNot(first, self.queue.enqueue("d", "track", "1", base_dir="/trial"))
        with mock.patch.object(self.queue, "_run", return_value={"path": "x"}):
            self.queue._run_task(self.queue.queue.pop(0))
        self.assertIsNot(first, self.queue.enqueue("d", "track", "1"))


class Listing(unittest.TestCase):
    def test_a_long_list_drops_finished_downloads_never_waiting_ones(self):
        queue = dq.DownloadQueue(workers=1)
        with mock.patch.object(dq.DownloadQueue, "start"):
            waiting = [queue.enqueue("d", "track", str(n)) for n in range(300)]
        for task in waiting[:250]:
            task.settled = True
        queue.snapshot()
        # The 50 oldest finished ones went; the 200 newest finished and the 50 waiting stayed.
        self.assertEqual(250, len(queue.tasks))
        self.assertTrue(all(t in queue.tasks for t in waiting[250:]))
        # Asking again for a waiting one joins it instead of queueing it twice.
        with mock.patch.object(dq.DownloadQueue, "start"):
            self.assertIs(waiting[299], queue.enqueue("d", "track", "299"))

    def test_the_list_can_be_limited_to_what_the_asker_may_see(self):
        queue = dq.DownloadQueue(workers=1)
        with mock.patch.object(dq.DownloadQueue, "start"):
            queue.enqueue("d", "track", "1", deezer_account="a")
            queue.enqueue("d", "track", "2", deezer_account="b")
        seen = queue.snapshot(lambda t: t.deezer_account == "a")
        self.assertEqual(["{'track_id': 1, 'add_to_playlist': False}"], [t["args"] for t in seen])


class Discography(unittest.TestCase):
    def test_releases_of_another_main_artist_are_left_out(self):
        queue = dq.DownloadQueue(workers=1)
        albums = [{"id": "1", "title": "Own album"}, {"id": "2", "title": "Compilation"}]
        task = dq.DownloadTask("d", "artist", "77")
        album = {"label": "Artist - Own album", "saved": 3, "total": 3, "failed": [], "replaced": []}
        with mock.patch.object(dq.deezer_dl, "artist_albums", return_value=albums), \
                mock.patch.object(dq.deezer_dl, "album_artist_id", side_effect=lambda a: "77" if a == "1" else "5080"), \
                mock.patch.object(queue, "_run_album", return_value=album) as run_album:
            summary = queue._run_artist(task)
        self.assertEqual(["1"], [c.args[1] for c in run_album.call_args_list])
        self.assertEqual(["Compilation"], summary["skipped"])


if __name__ == "__main__":
    unittest.main()
