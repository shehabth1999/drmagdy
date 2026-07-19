# -*- coding: utf-8 -*-
"""
drmagdy Module - Support Ticket Form View Patch.

Injects two fields into the support ticket form view
(key: ``support_supportticket_form_view``):
  - ``supervisor`` (FK to ``base.user``) after ``assigned_to``.
  - ``files`` (single image) after ``email``.

Both fields are injected into the ``support.ticket`` model by
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
        },
        {
            "operation": "after",
            "target": "field[name=email]",
            "content": {
                "name": "files",
                "widget": "files",
                "multiSelect": False,
                "string": _("Files"),
                "required": False,
                "readonly": False,
                "help": _("Image attached to this ticket"),
            },
        },
    ],
}
