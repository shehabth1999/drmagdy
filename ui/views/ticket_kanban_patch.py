# -*- coding: utf-8 -*-
"""
drmagdy Module - Support Ticket Kanban View Patch.

Patches the support ticket kanban card (parent key:
``support_ticket_kanban_view``) via Odoo-style view inheritance:

  - a red **Late** badge (``is_late``) first in the card header — drawn only
    on late tickets: the ``badge`` widget skips an off flag
    (``project/web/src/widgets/kanban/components/widgets/index.tsx``,
    ``utils/values.ts`` ``isEmptyValue``);
  - a FIXED card structure, one kind of item per block, so every card lines
    up the same way (the header is a label-less flow-wrap: with five items of
    different widths every card broke the line somewhere else and the date or
    the category landed wherever there was room — 2026-09-24 complaint):
      header  : priority stars · assignee chip · Late badge   (who + state)
      body    : Category · <chip>                             (labelled row)
      footer  : created date + time, label hidden             (always last)
    ``body`` / ``footer`` are added to the card with a ``modify`` on the
    direct path ``kanban.card`` (dict update), ``created_at`` is removed
    from the header. ``created_at`` shows date + time (``datetime`` widget);
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
            # Late badge: LAST in the header row (stars, assignee, then the
            # badge — user's call 2026-09-24); readonly keeps it out of the
            # quick-create form.
            "operation": "after",
            "target": "field[name=assigned_to]",
            "content": {
                "name": "is_late",
                "tag": "field",
                "widget": "badge",
                "color": "danger",
                "icon": "Clock",
                "readonly": True,
                "required": False,
                "string": _("Late"),
            },
        },
        {
            # The date leaves the header flow (it moves to the footer below).
            "operation": "remove",
            "target": "field[name=created_at]",
        },
        {
            # Body + footer blocks (the base card has header only). Ticket
            # "Type" = category, a labelled row of its own; the created
            # date + time always last, label hidden — a timestamp reads as a
            # footer line, not as a value to compare.
            "operation": "modify",
            "target": "kanban.card",
            "content": {
                "body": {
                    "fields": [
                        {
                            "name": "category",
                            "tag": "field",
                            "widget": "relation",
                            "displayField": "name",
                            "multiSelect": False,
                            "required": False,
                            "readonly": True,
                            "string": _("Category"),
                        },
                    ],
                },
                "footer": {
                    "left": [
                        {
                            "name": "created_at",
                            "tag": "field",
                            "widget": "datetime",
                            "required": False,
                            "readonly": True,
                            "hideLabel": True,
                            "string": _("Created On"),
                        },
                    ],
                },
            },
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
