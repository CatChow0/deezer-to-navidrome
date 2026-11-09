"""Long tasks (scans, downloads, rebuilds): their state, their events, and a way
to follow them without a stream. Android's event-stream client does not
reconnect by itself and stops in the background: an app can resume the stream
from the last event it got, or ask for the events after it here, waiting up to
25 s for the next one."""
import time

from flask import request

from core import config
from routes.api_v1 import api_v1_bp, error, ok
from routes.system import task_stream

MAX_WAIT = 25


def _summary(task) -> dict:
    return {**config.task_summary(task), "events": len(task["events"])}


@api_v1_bp.get("/tasks")
def tasks_list():
    """The tasks listed in Activity; changed_since: those changed after this
    time (seconds), for an app catching up."""
    since = request.args.get("changed_since", type=float)
    tasks = config.list_tasks()
    if since is not None:
        tasks = [t for t in tasks if (t.get("updated_at") or 0) > since]
    return ok({"tasks": tasks})


@api_v1_bp.get("/tasks/<task_id>")
def task_get(task_id):
    task = config.TASKS.get(task_id)
    if task is None:
        return error("not_found", "No such task.", 404)
    return ok({"task": _summary(task)})


@api_v1_bp.get("/tasks/<task_id>/events")
def task_events(task_id):
    """The events after index `after` (all of them without it). `wait`: up to
    25 s for the next one when there is none yet, unless the task is over."""
    task = config.TASKS.get(task_id)
    if task is None:
        return error("not_found", "No such task.", 404)
    after = request.args.get("after", default=-1, type=int)
    wait = min(max(request.args.get("wait", default=0, type=int), 0), MAX_WAIT)
    start = max(0, after + 1)
    deadline = time.monotonic() + wait
    with task["cond"]:
        while len(task["events"]) <= start and not task["done"]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            task["cond"].wait(timeout=remaining)
        events = list(task["events"][start:])
    return ok({
        "task": _summary(task),
        "events": [{"index": start + offset, **event} for offset, event in enumerate(events)],
        "after": start + len(events) - 1 if events else after,
    })


# The same stream as the web page's, under this prefix.
api_v1_bp.add_url_rule("/tasks/<task_id>/stream", "task_stream", task_stream)


@api_v1_bp.post("/tasks/<task_id>/cancel")
def task_cancel(task_id):
    if task_id not in config.TASKS:
        return error("not_found", "No such task.", 404)
    if not config.request_cancel(task_id):
        return error("not_cancellable", "This task cannot be stopped.", 409)
    return ok({"cancelling": task_id})
