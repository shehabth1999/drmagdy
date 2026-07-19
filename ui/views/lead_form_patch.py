# -*- coding: utf-8 -*-
"""
drmagdy Module - Lead Form View Patch.

Shows the ``payment_receipt`` image (FK to ``base.Attachment``) on the main
lead form (key: ``crm_lead_form_view``), right after ``assigned_to``.

The field is injected into ``crm.lead`` by ``LeadExtension`` in
``drmagdy/extensions.py`` and is populated by the chat-message action
``action_lead_won_from_receipt`` — so it is read-only here.
"""
from django.utils.translation import gettext as _


lead_form_drmagdy_receipt_patch = {
    "key": "lead_form_drmagdy_receipt_patch",
    "name": "Lead Form - drmagdy Payment Receipt",
    "model": "crm.lead",
    "view_type": "form",
    "priority": 50,
    "inherit_mode": "extension",
    "inherit_id": "crm_lead_form_view",
    "module": "drmagdy",
    "inheritance_operations": [
        {
            "operation": "after",
            "target": "field[name=assigned_to]",
            "content": {
                "name": "payment_receipt",
                "widget": "files",
                "multiSelect": False,
                "string": _("Payment Receipt"),
                "required": False,
                "readonly": True,
                "help": _("Payment receipt used to mark this lead as Won"),
            },
        }
    ],
}
