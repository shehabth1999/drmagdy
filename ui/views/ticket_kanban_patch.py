# -*- coding: utf-8 -*-
"""
drmagdy Module - Support Ticket Kanban View Patch.

Patches the support ticket kanban card (parent key:
``support_ticket_kanban_view``) via Odoo-style view inheritance:

  - adds the ``category`` relation to the card as the ticket **Type**
    (inserted right after ``assigned_to``), and
  - upgrades ``created_at`` from the date-only ``date`` widget to ``datetime``
    so the card shows the time as well.

The ``datetime`` widget is rendered by the kanban card FieldRenderer
(``project/web/src/widgets/kanban/components/widgets/index.tsx``).

Note: ``support.ticket`` has no ``type`` field; ``category`` (FK ->
``support.TicketCategory``) is the ticket's classification and is what we
surface as the "Type" on the card.
"""
from django.utils.translation import gettext as _


ticket_kanban_drmagdy_patch = {
    "key": "ticket_kanban_drmagdy_patch",
    "name": "Support Ticket Kanban - drmagdy Type + Datetime",
    "model": "support.ticket",
    "view_type": "kanban",
    "priority": 50,
    "inherit_mode": "extension",
    "inherit_id": "support_ticket_kanban_view",
    "module": "drmagdy",
    "inheritance_operations": [
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
    ],
}
