"""The download queue: a few worker threads fetching tracks from Deezer.

The shape of the queue is the one deezer-downloader exposed on its /queue
route, so the pages that read it keep working unchanged: each entry has a
state (`waiting`, `active`, `mission accomplished` or `failed`), the arguments
it was started with, its result and its exception.

Each download can also report its progress as it goes, through
`on_progress(stage, message, progress, short)`: `stage` is "queued" or
"downloading", `progress` a percentage (or None) and `short` a few characters
for a button ("Queued", "42%", "3/14").
"""
import threading
import traceback

from core import deezer_dl
from core.config import load_config

WAITING = "waiting"
ACTIVE = "active"
DONE = "mission accomplished"
FAILED = "failed"


class DownloadTask:
    def __init__(self, description, kind, music_id, on_done=None, on_progress=None):
        self.id = id(self)
        self.description = description
        self.kind = kind
        self.music_id = str(music_id)
        self.state = WAITING
        self.result = None
        self.exception = None
        self.progress = 0
        self.progress_maximum = 0
        self.finished_at = 0
        # Called with (task, result, error) once the download is over.
        self.on_done = on_done
        self.on_progress = on_progress

    @property
    def args(self):
        """The arguments, in the format the old queue used.

        The pages read them with a regex on 'track_id', so the names matter."""
        if self.kind == "album":
            return f"{{'album_id': {self.music_id}, 'add_to_playlist': False, 'create_zip': False}}"
        if self.kind == "artist":
            return f"{{'artist_id': {self.music_id}, 'add_to_playlist': False}}"
        return f"{{'track_id': {self.music_id}, 'add_to_playlist': False}}"

    def report(self, stage, message, progress=None, short=None):
        if not self.on_progress:
            return
        try:
            self.on_progress(stage, message, progress, short)
        except Exception:
            print(traceback.format_exc(), flush=True)

    def as_dict(self):
        return {
            "id": self.id,
            "description": self.description,
            "args": self.args,
            "state": self.state,
            "result": self.result,
            "exception": str(self.exception) if self.exception else "",
            "progress": [self.progress, self.progress_maximum],
        }


class DownloadQueue:
    def __init__(self, workers=4):
        self.lock = threading.Lock()
        self.tasks = []
        self.queue = []
        self.threads = []
        self.workers = workers
        self._started = False
        self.wakeup = threading.Condition(self.lock)

    def start(self):
        with self.lock:
            if self._started:
                return
            self._started = True
            for index in range(self.workers):
                thread = threading.Thread(target=self._worker, name=f"download-{index}", daemon=True)
                thread.start()
                self.threads.append(thread)

    def enqueue(self, description, kind, music_id, on_done=None, on_progress=None):
        task = DownloadTask(description, kind, music_id, on_done=on_done, on_progress=on_progress)
        with self.lock:
            active = sum(1 for t in self.tasks if t.state == ACTIVE)
            ahead = len(self.queue)
            # Said before the task is visible to the workers, so "Queued"
            # never arrives after "Starting".
            if active + ahead >= self.workers:
                message = f"Waiting for {ahead} other download{'s' if ahead != 1 else ''}" if ahead else "Waiting for a free slot"
                task.report("queued", message, None, "Queued")
            self.tasks.append(task)
            self.queue.append(task)
            self.wakeup.notify_all()
        self.start()
        return task

    def _worker(self):
        while True:
            # The workers wait for a task instead of leaving when the queue is
            # empty: a download queued later still has to be picked up. The
            # lock is released before the download, or reading the queue
            # would block for the whole download.
            with self.lock:
                while not self.queue:
                    self.wakeup.wait(0.5)
                task = self.queue.pop(0)
                task.state = ACTIVE
            self._run_task(task)

    def _run_task(self, task):
        task.report("downloading", "Starting", 0, "0%")
        try:
            task.result = self._run(task)
            task.state = DONE
        except Exception as e:
            print(traceback.format_exc(), flush=True)
            task.exception = e
            task.state = FAILED
        task.finished_at = 1
        if task.on_done:
            try:
                task.on_done(task, task.result, task.exception)
            except Exception:
                print(traceback.format_exc(), flush=True)

    # ── Kinds of downloads ─────────────────────────────────────────────────────

    def _run(self, task):
        if task.kind == "track":
            return self._run_track(task)
        if task.kind == "album":
            return self._run_album(task, task.music_id)
        if task.kind == "artist":
            return self._run_artist(task)
        raise ValueError(f"Unknown download type: {task.kind}")

    def _run_track(self, task):
        summary = {"label": "", "saved": 0, "total": 1, "failed": [], "already": False}
        last = {"percent": -1}

        def on_start(song, already):
            summary["label"] = deezer_dl.song_label(song)
            summary["already"] = already
            if not already:
                task.report("downloading", summary["label"], 0, "0%")

        def on_bytes(received, total):
            if not total:
                return
            percent = min(99, int(received * 100 / total))
            # A message every 5 % is enough to move the bar.
            if percent - last["percent"] >= 5:
                last["percent"] = percent
                task.progress, task.progress_maximum = percent, 100
                task.report("downloading", summary["label"], percent, f"{percent}%")

        path = deezer_dl.download_track(task.music_id, on_start=on_start, on_bytes=on_bytes)
        summary.update({"saved": 1, "path": str(path)})
        return summary

    def _run_album(self, task, album_id, on_track_done=None):
        summary = {"label": "", "saved": 0, "total": 0, "failed": [], "files": []}

        def on_start(songs):
            first = songs[0]
            summary["label"] = f"{first.get('ALB_ART_NAME') or first.get('ART_NAME')} - {first.get('ALB_TITLE')}"
            summary["total"] = len(songs)
            task.progress_maximum = len(songs)
            if not on_track_done:
                task.report("downloading", f"0/{len(songs)} tracks", 0, f"0/{len(songs)}")

        def on_track(song, path, error):
            if error:
                summary["failed"].append(deezer_dl.song_label(song))
            else:
                summary["saved"] += 1
                summary["files"].append(str(path))
            done = summary["saved"] + len(summary["failed"])
            task.progress = done
            if on_track_done:
                on_track_done(done, summary["total"], song)
            else:
                total = summary["total"]
                task.report(
                    "downloading",
                    f"{done}/{total}: {deezer_dl.song_label(song)}",
                    round(done * 100 / total) if total else None,
                    f"{done}/{total}",
                )

        deezer_dl.download_album(album_id, on_start=on_start, on_track=on_track)
        return summary

    def _run_artist(self, task):
        albums = deezer_dl.artist_albums(task.music_id)
        if not albums:
            raise deezer_dl.DeezerDownloadError("Deezer lists no release for this artist")
        summary = {"label": "", "saved": 0, "total": 0, "failed": [], "albums": len(albums)}
        for index, album in enumerate(albums):
            def on_track_done(done, total, song, index=index, album=album):
                share = (index + (done / total if total else 1)) / len(albums)
                task.report(
                    "downloading",
                    f"Release {index + 1}/{len(albums)}: {album['title']} ({done}/{total})",
                    round(share * 100),
                    f"{index + 1}/{len(albums)}",
                )

            try:
                result = self._run_album(task, album["id"], on_track_done=on_track_done)
            except Exception as e:
                summary["failed"].append(f"{album['title']} ({e})")
                continue
            if not summary["label"]:
                summary["label"] = result["label"].split(" - ")[0]
            summary["saved"] += result["saved"]
            summary["total"] += result["total"]
            summary["failed"] += result["failed"]
        return summary

    def snapshot(self):
        with self.lock:
            # The old entries are dropped so the list does not grow forever.
            if len(self.tasks) > 200:
                self.tasks = self.tasks[-200:]
            return [t.as_dict() for t in self.tasks]


_queue = None
_queue_lock = threading.Lock()


def get_queue():
    """The queue, started with the configured number of workers."""
    global _queue
    with _queue_lock:
        if _queue is None:
            workers = 4
            try:
                workers = max(1, int(load_config().get("download_workers", 4)))
            except Exception:
                pass
            _queue = DownloadQueue(workers=workers)
            _queue.start()
        return _queue


def enqueue_download(kind, music_id, on_done=None, on_progress=None):
    """Puts a download in the queue and returns the task."""
    description = f"Downloading {kind} {music_id}"
    return get_queue().enqueue(description, kind, music_id, on_done=on_done, on_progress=on_progress)


def queue_snapshot():
    return get_queue().snapshot()
