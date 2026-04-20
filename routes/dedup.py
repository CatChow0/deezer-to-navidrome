import threading
import time

from flask import Blueprint, jsonify, request

from core.config import create_task, push_task_event, TASKS
from core.dedup import apply_dedup_decisions, load_dedup_report, run_dedup_analysis

dedup_bp = Blueprint("dedup", __name__)


@dedup_bp.post("/dedup/start")
def dedup_start():
    task_id = create_task()

    def on_progress(message=None, progress=None, stage=None, payload=None):
        push_task_event(task_id, message=message, progress=progress, stage=stage)
        if payload is not None:
            task = TASKS.get(task_id)
            if task:
                task["queue"].put(
                    {
                        "type": "dedup_result",
                        "payload": payload,
                        "timestamp": int(time.time()),
                    }
                )

    def runner():
        try:
            push_task_event(task_id, "Initializing duplicate analysis", stage="init", progress=0)
            report = run_dedup_analysis(progress_cb=on_progress)
            push_task_event(
                task_id,
                f"Dedup done: {report['group_count']} group(s)",
                stage="done",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(task_id, f"Dedup error: {e}", stage="error", done=True, error=True)

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})


@dedup_bp.get("/dedup/report")
def dedup_report_route():
    report = load_dedup_report()
    if not report:
        return jsonify({"ok": False, "error": "No deduplication report found"}), 404
    return jsonify({"ok": True, "report": report})


@dedup_bp.post("/dedup/apply")
def dedup_apply_route():
    payload = request.get_json(silent=True) or {}
    decisions = payload.get("decisions", [])
    mode = payload.get("mode", "quarantine")
    if not decisions:
        return jsonify({"ok": False, "error": "No decisions provided"}), 400
    result = apply_dedup_decisions(decisions, mode=mode)
    return jsonify({"ok": True, **result})
