# -*- coding: utf-8 -*-
"""
drmagdy Module - Support Ticket Form View Patch.

Injects two fields into the support ticket form view
(key: ``support_supportticket_form_view``):
  - ``supervisor`` (FK to ``base.user``) after ``assigned_to``.
  - ``files`` (multiple images, M2M) after ``email``.

Both fields are injected into the ``support.ticket`` model by
``TicketExtension`` in ``drmagdy/extensions.py``.

Also appends the ``Send to WhatsApp`` header action button (menu-type): opens
the ``drmagdy_send_ticket_image_form_view`` wizard (slideover) to send the
ticket's image to WhatsApp conversations. Handler:
``Ticket.action_send_ticket_image_to_conversations(queryset, form)``.
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
                "multiSelect": True,
                "accept": "image/*",
                "string": _("Files"),
                "required": False,
                "readonly": False,
                "help": _("Images attached to this ticket"),
            },
        },
        # Menu-type action: opens the SendTicketImageAction wizard (slideover)
        # to send this ticket's image to WhatsApp conversations. Handler:
        # Ticket.action_send_ticket_image_to_conversations(queryset, form)
        # (TicketExtension, drmagdy/extensions.py). Hidden when the ticket has
        # no image.
        {
            "operation": "append",
            "target": "header.actions",
            "content": [
                {
                    "name": "action_send_ticket_image_to_conversations",
                    "string": _("Send to WhatsApp"),
                    "icon": "Send",
                    "type": "menu",
                    "as": "button",
                    "variant": "success",
                    "view_key": "drmagdy_send_ticket_image_form_view",
                    "menu_type": "slideover",
                    "view_type": ["form"],
                    # Managers + admins only (admins imply managers; superusers
                    # bypass). Enforced server-side too, in the @action handler.
                    "allowed_groups": ["support.managers"],
                    # Hide when the ticket has no images. `files` is an M2M so an
                    # empty value serializes as [] (not null): is_null alone won't
                    # match. String([]) === "" in JS, so eq "" hides on an empty
                    # array; the is_null branch also covers a null value.
                    "invisible": {"or": [
                        {"field": "files", "operator": "is_null"},
                        {"field": "files", "operator": "eq", "value": ""},
                    ]},
                },
            ],
        },
    ],
}
