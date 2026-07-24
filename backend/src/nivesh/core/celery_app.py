"""Celery application instance.

Ingestion and AI-orchestration tasks register against this app instance.
Per the approved architecture, ingestion workers and orchestration workers
are deployed as separate processes/queues in production even though they
share this one app definition in the scaffold -- see docs/v2
10-V2-System-Architecture.md.
"""

from celery import Celery

from nivesh.config import get_settings

settings = get_settings()

celery_app = Celery(
    "nivesh",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["nivesh.ingestion.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
)
