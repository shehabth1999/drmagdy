# -*- coding: utf-8 -*-
"""Celery tasks for the drmagdy extension.

Discovered automatically: ``project/celery.py`` calls ``autodiscover_tasks()``
with no arguments, which imports ``<AppConfig.name>.tasks`` for every installed
app — including this top-level extension app — so the task registers as
``drmagdy.tasks.notify_due_ticket_arrivals``.

Scheduling lives in the database (django-celery-beat ``DatabaseScheduler``):
migration ``0005_beat_notify_due_arrivals`` creates the ``PeriodicTask`` row
(every 5 minutes). A running beat reloads it within ~30 s; no restart needed.
"""
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="drmagdy.tasks.notify_due_ticket_arrivals")
def notify_due_ticket_arrivals():
    """Alert ONLINE users once when an ordered item's expected arrival time has
    passed and the ticket is still in "اصناف تحت الطلب".

    Contract (agreed with the customer, 2026-09-14):
    * only tickets in the under-order stage, not cancelled, not yet notified;
    * recipients = users currently online (chat presence, i.e. any ERP tab
      open), excluding AI agents and users without a partner;
    * once per arming: ``arrival_notified_at`` is stamped after the send and
      cleared by ``TicketExtension.pre_save`` whenever the expected date
      changes or the ticket re-enters the under-order stage;
    * if nobody is online (or presence is unavailable) nothing is marked, so the
      next tick retries — the alert is never lost, only delayed.
    """
    from modules.base.models.menu_item import MenuItem
    from modules.base.models.user import User
    from modules.chat import presence
    from modules.notifications.services import post_notification
    from modules.support.models import Ticket

    from . import ticket_stages as st
    from .extensions import compute_ribbon_state

    now = timezone.now()
    under_order = st.stage_id(st.UNDER_ORDER)
    if not under_order:
        return {"skipped": "under-order stage not found"}

    due = list(
        Ticket.all_objects.filter(
            stage_id=under_order,
            active=True,
            is_cancelled=False,
            arrival_notified_at__isnull=True,
            expected_arrival_at__lte=now,
        )
        .select_related("partner")
        .order_by("expected_arrival_at")
    )
    if not due:
        return {"due": 0}

    online_ids = {int(uid) for uid in presence.get_all_online_user_ids() if str(uid).isdigit()}
    if not online_ids:
        # [] means "nobody online" OR "Redis unavailable" — either way, retry later.
        logger.info("drmagdy: %d ticket(s) due but no online users; will retry next tick", len(due))
        return {"due": len(due), "online": 0}

    partner_ids = list(
        User.objects.filter(pk__in=online_ids, is_active=True, ai_agent=False, partner__isnull=False)
        .values_list("partner_id", flat=True)
        .distinct()
    )
    if not partner_ids:
        return {"due": len(due), "online": len(online_ids), "recipients": 0}

    notified = 0
    for ticket in due:
        when = timezone.localtime(ticket.expected_arrival_at).strftime("%Y-%m-%d %H:%M")
        customer = ticket.partner.name if ticket.partner_id and ticket.partner else "-"
        subject = "موعد وصول صنف تحت الطلب"
        body = (
            f"التذكرة #{ticket.id} «{ticket.name}» للعميل {customer}: "
            f"موعد الوصول المتوقع {when} وما زالت في «اصناف تحت الطلب»."
        )
        try:
            url = MenuItem.get_url_for_model(ticket, view_type="form", id=ticket.id)
        except Exception:  # noqa: BLE001 - a broken deep link must not block the alert
            logger.exception("drmagdy: could not build ticket url for #%s", ticket.pk)
            url = "/"

        post_notification(
            partner_ids=partner_ids,
            subject=subject,
            body=body,
            record=ticket,
            is_push=True,
            url=url,
            category="general",
        )

        # .update(): no lifecycle hooks, so pre_save cannot re-arm what we just stamped.
        Ticket.all_objects.filter(pk=ticket.pk).update(
            arrival_notified_at=now,
            ribbon_state=compute_ribbon_state(ticket, now),
        )

        try:
            ticket.message_post(body="تجاوز موعد الوصول المتوقع ولم يصل الصنف بعد.", message_type="note")
        except Exception:  # noqa: BLE001 - chatter is best effort
            logger.exception("drmagdy: chatter note failed for ticket #%s", ticket.pk)

        notified += 1

    logger.info("drmagdy: arrival alerts sent for %d ticket(s) to %d recipient(s)", notified, len(partner_ids))
    return {"due": len(due), "notified": notified, "recipients": len(partner_ids)}
