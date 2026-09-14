# -*- coding: utf-8 -*-
"""Register the arrival-reminder periodic task with django-celery-beat.

Runs ``drmagdy.tasks.notify_due_ticket_arrivals`` every 5 minutes. Idempotent
(update_or_create by name). Historical models used inside a migration do NOT
fire django-celery-beat's change signals, so the ``PeriodicTasks`` marker row is
bumped explicitly — a running beat (DatabaseScheduler) then reloads within
``CELERY_BEAT_MAX_LOOP_INTERVAL`` seconds, no restart needed.
"""
from django.db import migrations
from django.utils import timezone

TASK_NAME = "drmagdy: notify due ticket arrivals"
TASK_PATH = "drmagdy.tasks.notify_due_ticket_arrivals"


def _bump(apps):
    PeriodicTasks = apps.get_model("django_celery_beat", "PeriodicTasks")
    PeriodicTasks.objects.update_or_create(ident=1, defaults={"last_update": timezone.now()})


def forward(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # No unique constraint on (every, period): pick an existing row or create one.
    every_5_min = IntervalSchedule.objects.filter(every=5, period="minutes").order_by("id").first()
    if every_5_min is None:
        every_5_min = IntervalSchedule.objects.create(every=5, period="minutes")

    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={
            "task": TASK_PATH,
            "interval": every_5_min,
            "crontab": None,
            "solar": None,
            "clocked": None,
            "one_off": False,
            "enabled": True,
            "description": (
                "drmagdy: alert online users when a ticket under order reaches its "
                "expected arrival time (see extensions/drmagdy/tasks.py)"
            ),
        },
    )
    _bump(apps)


def backward(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()
    _bump(apps)


class Migration(migrations.Migration):

    dependencies = [
        ("drmagdy", "0004_cancelticketaction"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(forward, backward)]
