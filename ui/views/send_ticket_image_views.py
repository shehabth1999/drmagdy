# -*- coding: utf-8 -*-
"""
drmagdy Module - "Send Ticket Image" wizard form view.

Model: ``drmagdy.sendticketimageaction`` (TransientModel in ``drmagdy/models.py``).
Opened as a slideover by the ``Send to WhatsApp`` menu-type button injected into
the support ticket form view (see ``ticket_form_patch.py``). On submit, the
framework saves the transient record and calls
``Ticket.action_send_ticket_image_to_conversations(queryset, form)``
(defined on ``TicketExtension`` in ``drmagdy/extensions.py``).

Flow: pick a WhatsApp number → the Customers picker narrows (via the
``@onchange('whatsapp_account')`` dynamic domain) to partners who have a
conversation on that number, shown by their name → optional caption message.
"""
from django.utils.translation import gettext as _


send_ticket_image_form_view = {
    "key": "drmagdy_send_ticket_image_form_view",
    "name": _("Send Ticket Image"),
    "model": "drmagdy.sendticketimageaction",
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
                                    "name": "whatsapp_account",
                                    "string": _("WhatsApp Number"),
                                    "widget": "relation",
                                    "displayField": "name",
                                    "multiSelect": False,
                                    "required": True,
                                    "onChange": True,
                                    "help": _("The WhatsApp account (number) to send from."),
                                    "domain": {
                                        "filters": {
                                            "operator": "and",
                                            "filters": [
                                                {"field": "active", "operator": "eq", "value": True},
                                            ],
                                        }
                                    },
                                },
                                {
                                    "name": "partners",
                                    "string": _("Customers"),
                                    "widget": "relation",
                                    "displayField": "name",
                                    "multiSelect": True,
                                    "required": True,
                                    # Locked until a number is picked — guarantees the
                                    # picker only ever offers customers whose conversation
                                    # is on the SELECTED number (the @onchange narrows the
                                    # domain when whatsapp_account changes), so the send
                                    # can never hit "no conversation on this number".
                                    "readonly": {"field": "whatsapp_account", "operator": "is_null"},
                                    "help": _("Customers to send the image to — pick the WhatsApp number first."),
                                    "placeholder": _("Select a WhatsApp number first..."),
                                    # The dependency lives in the STATIC domain via a live
                                    # form-value placeholder — no reliance on onchange.
                                    # `in` (not `eq`): when no number is picked yet the
                                    # placeholder resolves to [null] → SQL `IN (NULL)`
                                    # matches NOTHING (an unresolved `eq` null fails
                                    # pydantic validation and the selection endpoint
                                    # would silently drop the whole domain → ALL
                                    # partners). Verified: [null]→0 rows, [id]→exact.
                                    "domain": {
                                        "filters": {
                                            "operator": "and",
                                            "filters": [
                                                {"field": "social_conversations__type", "operator": "eq", "value": "whatsapp"},
                                                {"field": "social_conversations__social_account_object_id", "operator": "in", "value": ["{{whatsapp_account.id}}"]},
                                            ],
                                        }
                                    },
                                },
                                {
                                    "name": "message",
                                    "string": _("Message"),
                                    "widget": "textarea",
                                    "rows": 4,
                                    "required": False,
                                    "placeholder": _("Optional message sent with the image..."),
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    },
}
