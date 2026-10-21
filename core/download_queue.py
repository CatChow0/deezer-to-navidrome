"""The download queue: a few worker threads fetching tracks from Deezer.

The shape of the queue is the one deezer-downloader exposed on its /queue
route, so the pages that read it keep working unchanged: each entry has a
state (`waiting`, `active`, `mission accomplished` or `failed`), the arguments
it was started with, its result and its exception.
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
    def __init__(self, description, kind, music_id, on_done=None):
        self.id = id(self)
        self.description = description
        self.kind = kind
        self.music_id = str(music_id)
        self.state = WAITING
        self.result = None
        self.exception = None
        self.progress = 0
        self.progress_maximum = 0
        self.created_at = 0
        self.finished_at = 0
        # Called with (task, result, error) once the download is over.
        self.on_done = on_done

    @property
    def args(self):
        """The arguments, in the format the old queue used.

        The pages read them with a regex on 'track_id', so the names matter."""
        if self.kind == "album":
            return f"{{'album_id': {self.music_id}, 'add_to_playlist': False, 'create_zip': False}}"
        return f"{{'track_id': {self.music_id}, 'add_to_playlist': False}}"

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

    def enqueue(self, description, kind, music_id, on_done=None):
        task = DownloadTask(description, kind, music_id, on_done=on_done)
        with self.lock:
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
            self._run_task(task)

    def _run_task(self, task):
        task.state = ACTIVE
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

    def _run(self, task):
        if task.kind == "track":
            path = deezer_dl.download_track(task.music_id)
            return str(path)
        if task.kind == "album":
            failed = []

            def on_track(song, path, error):
                if error:
                    failed.append(f"{song.get('ART_NAME')} - {song.get('SNG_TITLE')}")

            files = deezer_dl.download_album(task.music_id, on_track=on_track)
            return {"files": [str(f) for f in files], "failed": failed}
        raise ValueError(f"Unknown download type: {task.kind}")

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


def enqueue_download(kind, music_id, on_done=None):
    """Puts a download in the queue and returns the task."""
    description = f"Downloading {kind} {music_id}"
    return get_queue().enqueue(description, kind, music_id, on_done=on_done)


def queue_snapshot():
    return get_queue().snapshot()
