"""Celery application: run orchestration tasks off the request path."""
from __future__ import annotations

from ..config import get_settings

settings = get_settings()

try:
    from celery import Celery

    celery_app = Celery(
        "orchestrator",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )
    celery_app.conf.task_track_started = True
    celery_app.conf.result_expires = 3600

    @celery_app.task(name="orchestrator.run_task")
    def run_task_async(task: str) -> dict:
        from ..graph import run_task

        result = run_task(task)
        return {
            "task_id": result.get("task_id"),
            "answer": result.get("answer"),
            "escalated": result.get("escalated", False),
            "quality": result.get("quality"),
        }

except Exception:  # pragma: no cover - Celery optional
    celery_app = None

    def run_task_async(task: str) -> dict:
        from ..graph import run_task

        result = run_task(task)
        return {"task_id": result.get("task_id"), "answer": result.get("answer")}
