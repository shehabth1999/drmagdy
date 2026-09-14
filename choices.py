# -*- coding: utf-8 -*-
"""Shared choice lists for the drmagdy ticket workflow.

Kept in their own module so both ``models.py`` (the CancelTicketAction wizard)
and ``extensions.py`` (fields injected into support.ticket) can import them
without creating an import cycle.
"""
from django.utils.translation import gettext_lazy as _


# Outcome of sales contacting the customer once the ordered item has arrived
# (stage "اصناف وصلت"). Plain choices, no relation, per product request.
CONTACT_STATUS_CHOICES = [
    ("no_answer", _("No answer")),
    ("contacted_waiting", _("Contacted, awaiting reply")),
    ("contacted_will_pickup", _("Contacted, will pick up")),
    ("delivered", _("Delivered")),
]

# What the cancel wizard does with the ordered item.
CANCEL_MODE_CHOICES = [
    ("cancel_keep", _("Cancelled, keep the item")),
    ("cancel_return", _("Returned to the shelf")),
]

# Value shown on the form ribbon. Stored on the ticket (``ribbon_state``) and
# recomputed on every save (and by the arrival reminder task) so the ribbon
# reflects persisted truth. Precedence is decided in
# ``extensions.compute_ribbon_state``.
RIBBON_CHOICES = [
    ("cancelled", _("Cancelled")),
    ("overdue", _("Item has not arrived yet")),
    ("returned", _("Cancelled and returned")),
    ("very_important", _("Obtain from anywhere")),
    ("urgent", _("Urgent")),
]
