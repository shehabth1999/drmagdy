# -*- coding: utf-8 -*-
"""
drmagdy Module - "Cancel Order" wizard form view.

Model: ``drmagdy.cancelticketaction`` (TransientModel in ``drmagdy/models.py``).
Opened as a slideover by the ``Cancel Order`` menu-type button injected into the
support ticket form (see ``ticket_form_patch.py``). On submit the framework
saves the transient record and calls
``Ticket.action_cancel_ticket(queryset, form)`` (``TicketExtension`` in
``drmagdy/extensions.py``).

Two outcomes, chosen in ``mode``:
  - cancel_keep   → ticket closes into "تمت المعالجة", flagged cancelled.
  - cancel_return → return to supplier (مرتجع شراء صنف): the SAME ticket
                    restarts in "جديد", flagged returned, category set
                    automatically to the purchase-return category.
"""
from django.utils.translation import gettext as _


cancel_ticket_form_view = {
    "key": "drmagdy_cancel_ticket_form_view",
    "name": _("Cancel Order"),
    "model": "drmagdy.cancelticketaction",
    "view_type": "form",
    "priority": 1,
    "module": "drmagdy",
    "body": {
        "sheet": {
            "sections": [
                {
                    "title": "",
                    "groups": [
                        {
                            "fullWidth": True,
                            "fields": [
                                {
                                    "name": "mode",
                                    "string": _("What happens to the item?"),
                                    # Options come from the model's choices automatically.
                                    "widget": "select",
                                    "required": True,
                                    "defaultValue": "cancel_keep",
                                    "help": _("Keep it (ticket closes as cancelled) or return it to the supplier (same ticket restarts as new with the purchase-return category)."),
                                },
                                {
                                    "name": "reason",
                                    "string": _("Reason"),
                                    "widget": "textarea",
                                    "rows": 3,
                                    "required": False,
                                    "placeholder": _("Optional reason, saved in the ticket chatter..."),
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    },
}
