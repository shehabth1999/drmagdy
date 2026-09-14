# -*- coding: utf-8 -*-
"""Shared choice lists for the drmagdy ticket workflow.

Kept in their own module so both ``models.py`` (the CancelTicketAction wizard)
and ``extensions.py`` (fields injected into support.ticket) can import them
without creating an import cycle.
"""
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy


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
    ("cancel_return", _("Return to supplier")),
]

# Value shown on the form ribbon. Stored on the ticket (``ribbon_state``) and
# recomputed on every save (and by the arrival reminder task) so the ribbon
# reflects persisted truth. Precedence is decided in
# ``extensions.compute_ribbon_state``.
# Labels are deliberately ONE word (or two short ones): the ribbon is a small
# diagonal strip and long text is clipped.
# ``pgettext_lazy("ribbon", ...)``: generic msgids such as "Cancelled" exist in
# other modules' catalogues, and Django's merged catalogue gives an extension
# (last in INSTALLED_APPS) the lowest priority — the context keeps OUR words.
RIBBON_CHOICES = [
    ("cancelled", pgettext_lazy("ribbon", "Cancelled")),
    ("overdue", pgettext_lazy("ribbon", "Overdue")),
    ("returned", pgettext_lazy("ribbon", "Returned")),
    ("very_important", pgettext_lazy("ribbon", "Very important")),
    ("urgent", pgettext_lazy("ribbon", "Urgent")),
]
