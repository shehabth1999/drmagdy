# -*- coding: utf-8 -*-
"""
drmagdy Module - Support Ticket Form View Patch.

Injects the ``supervisor`` field (FK to ``base.user``) into the support ticket
form view (key: ``support_supportticket_form_view``), right after the
``assigned_to`` field in the first group.

The field itself is injected into the ``support.ticket`` model by
``TicketExtension`` in ``drmagdy/extensions.py``.
"""
from django.utils.translation import gettext as _


ticket_form_drmagdy_supervisor_patch = {
    "key": "ticket_form_drmagdy_supervisor_patch",
    "name": "Support Ticket Form - drmagdy Supervisor",
    "model": "support.ticket",
    "view_type": "form",
    "priority": 50,
    "inherit_mode": "extension",
    "inherit_id": "support_supportticket_form_view",
    "module": "drmagdy",
    "inheritance_operations": [
        {
            "operation": "after",
            "target": "field[name=assigned_to]",
            "content": {
                "name": "supervisor",
                "string": _("Supervisor"),
                "widget": "relation",
                "displayField": "name",
                "multiSelect": False,
                "required": False,
                "readonly": False,
                "placeholder": _("Select supervisor..."),
                "help": _("Supervisor responsible for this ticket"),
            },
        }
    ],
}
