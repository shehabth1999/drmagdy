# -*- coding: utf-8 -*-
"""
drmagdy Module - Support Ticket Kanban View Patch.

Patches the support ticket kanban card (parent key:
``support_ticket_kanban_view``) via Odoo-style view inheritance:

  - a red **Late** badge (``is_late``) first in the card header — drawn only
    on late tickets: the ``badge`` widget skips an off flag
    (``project/web/src/widgets/kanban/components/widgets/index.tsx``,
    ``utils/values.ts`` ``isEmptyValue``);
  - the ``category`` relation as the ticket **Type** (after ``assigned_to``);
  - ``created_at`` upgraded from the date-only ``date`` widget to ``datetime``;
  - **late tickets first** in every column, then newest first:
    ``body.kanban.order_by`` is the board's default card order
    (``modules/base/views/kanban_paginated_view.py``); a sort picked in the
    search bar still wins. The ``kanban`` selector resolves to the board's
    config block (``ui_view.py`` ``_is_element_type``), so the ``modify``
    lands on ``body.kanban`` and not on the body root. ``drmagdy/tests.py``
    applies these operations to the base body and asserts both.

``is_late`` is a real column on ``support_ticket`` (``TicketExtension``,
recomputed on save and by the arrival reminder task) because the filter engine
can only ORDER by columns — a Python property would show but never sort.

Labels are plain English here and translated on the card by the frontend
catalogue (``gettext(field.string)``), like "Category" always was; "Late" is
in the merged catalogue ("متأخر").

Note: ``support.ticket`` has no ``type`` field; ``category`` (FK ->
``support.TicketCategory``) is the ticket's classification and is what we
surface as the "Type" on the card.
"""
from django.utils.translation import gettext as _


ticket_kanban_drmagdy_patch = {
    "key": "ticket_kanban_drmagdy_patch",
    "name": "Support Ticket Kanban - drmagdy Late badge, Type, Datetime",
    "model": "support.ticket",
    "view_type": "kanban",
    "priority": 50,
    "inherit_mode": "extension",
    "inherit_id": "support_ticket_kanban_view",
    "module": "drmagdy",
    "inheritance_operations": [
        {
            # Late badge: first in the header row so it is the first thing the
            # eye meets; readonly keeps it out of the quick-create form.
            "operation": "before",
            "target": "field[name=priority]",
            "content": {
                "name": "is_late",
                "tag": "field",
                "widget": "badge",
                "color": "danger",
                "readonly": True,
                "required": False,
                "string": _("Late"),
            },
        },
        {
            # Ticket "Type" = category. Relation widget mirrors how assigned_to
            # renders on the card; readonly since the card is a quick glance.
            "operation": "after",
            "target": "field[name=assigned_to]",
            "content": {
                "name": "category",
                "tag": "field",
                "widget": "relation",
                "displayField": "name",
                "multiSelect": False,
                "required": False,
                "readonly": True,
                "string": _("Category"),
            },
        },
        {
            # created_at should show date + time, not just the date.
            "operation": "modify",
            "target": "field[name=created_at]",
            "content": {"widget": "datetime"},
        },
        {
            # Late tickets first in every column, then the model's own order
            # (newest first). Kanban only: the list keeps Meta.ordering.
            "operation": "modify",
            "target": "kanban",
            "content": {"order_by": ["-is_late", "-created_at"]},
        },
    ],
}
