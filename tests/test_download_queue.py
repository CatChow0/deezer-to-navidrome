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
