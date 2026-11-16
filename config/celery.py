"""Celery app (broker: Redis). Tasks live in apps/*/tasks.py."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("webspeed")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
