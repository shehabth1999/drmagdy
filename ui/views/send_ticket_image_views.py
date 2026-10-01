# -*- coding: utf-8 -*-
"""
drmagdy Module - "Send Ticket Image" wizard form view.

Model: ``drmagdy.sendticketimageaction`` (TransientModel in ``drmagdy/models.py``).
Opened as a slideover by the ``Send to WhatsApp`` menu-type button injected into
the support ticket form view (see ``ticket_form_patch.py``). On submit, the
framework saves the transient record and calls
``Ticket.action_send_ticket_image_to_conversations(queryset, form)``
(defined on ``TicketExtension`` in ``drmagdy/extensions.py``).

Flow: pick a WhatsApp number — a WhatsApp Web connection or a WhatsApp API
account, both listed in ONE dropdown (see ``drmagdy/whatsapp_lines.py``) → the
Customers picker narrows (via the ``@onchange('whatsapp_line')`` dynamic
domain) to partners who have a conversation on that number, shown by their
name → optional caption message.

The dropdown's options, its default and the Customers domain of that default
are resolved when the view is SYNCED (the dict is stored in the DB): re-run
``sync_ui_views`` after connecting, renaming or removing a number.
"""
from django.utils.translation import gettext as _

from drmagdy.whatsapp_lines import customers_domain, default_line, line_options


def _resolve_lines():
    """``(options, default)`` of the number dropdown; empty when the account
    tables are not there yet (early import), so the view stays importable."""
    try:
        options = line_options()
        default = default_line()
    except Exception:  # pragma: no cover - table missing / early import
        return [], None
    # Never default to a line the dropdown does not offer.
    if default not in {option["value"] for option in options}:
        default = None
    return options, default


_LINE_OPTIONS, _DEFAULT_LINE = _resolve_lines()

_NO_LINE = {"or": [
    {"field": "whatsapp_line", "operator": "is_null"},
    {"field": "whatsapp_line", "operator": "eq", "value": ""},
]}


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
                                    "name": "whatsapp_line",
                                    "string": _("WhatsApp Number"),
                                    "widget": "select",
                                    # A list (not a dict) keeps the order: the
                                    # stored JSON would re-sort dict keys.
                                    "options": _LINE_OPTIONS,
                                    "required": True,
                                    "onChange": True,
                                    # Pre-selected number (see whatsapp_lines.default_line);
                                    # the Customers picker is filtered by it from the start.
                                    **({"defaultValue": _DEFAULT_LINE} if _DEFAULT_LINE else {}),
                                    "help": _("The number to send from: a WhatsApp Web connection or a WhatsApp API account."),
                                },
                                {
                                    "name": "partners",
                                    "string": _("Customers"),
                                    "widget": "relation",
                                    "displayField": "name",
                                    "multiSelect": True,
                                    "required": True,
                                    # Locked until a number is picked.
                                    "readonly": _NO_LINE,
                                    "help": _("Customers to send the image to — pick the WhatsApp number first."),
                                    "placeholder": _("Select a WhatsApp number first..."),
                                    # Customers of the DEFAULT number: no onchange
                                    # fires for a default value, so the form must
                                    # open already filtered. Picking another number
                                    # replaces this with that number's customers
                                    # (dynamic domain returned by the onchange). If
                                    # the two ever disagree the send handler refuses
                                    # the whole send and names the customers that
                                    # have no conversation on the picked number.
                                    "domain": customers_domain(_DEFAULT_LINE),
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
