# -*- coding: utf-8 -*-
"""
drmagdy Module - Bank Roshtat (prescription bank) list + form views.

Model: ``drmagdy.bankroshtat`` (defined in ``drmagdy/models.py``).
Rows are created from a single chat image message via the server action
``action_create_bank_roshtat_from_message`` (``drmagdy/extensions.py``).
"""
from django.utils.translation import gettext as _


bank_roshtat_list_view = {
    "key": "drmagdy_bank_roshtat_list_view",
    "name": "Bank Roshtat",
    "model": "drmagdy.bankroshtat",
    "menu_item": "drmagdy_main_menu_bank_roshtat",
    "view_type": "list",
    "priority": 10,
    "module": "drmagdy",
    "body": {
        # Toolbar action (enabled when a row is selected). The per-row `buttons`
        # column below resolves its `action_name` against this list.
        "header": {
            "actions": [
                {
                    "string": _("Open Conversation"),
                    "icon": "MessageSquare",
                    "name": "action_open_conversation",
                    "type": "server",
                    "as": "button",
                    "variant": "primary",
                    "selection_required": True,
                    "confirm_required": False,
                },
            ],
        },
        "tree": {
            "fields": [
                {
                    "name": "attachment",
                    "widget": "image",
                    "string": _("Image"),
                    "help": _("Prescription image"),
                    "visible": True,
                    "readonly": True,
                    "width": 120,
                },
                {
                    "name": "name",
                    "widget": "text",
                    "string": _("Name"),
                    "help": _("Auto-generated from the chat message"),
                    "visible": True,
                    "editor": True,
                    "width": 300,
                },
                {
                    "name": "created_at",
                    "widget": "datetime",
                    "string": _("Created On"),
                    "help": _("Date and time this row was created"),
                    "visible": True,
                    "editor": False,
                    "readonly": True,
                    "width": 180,
                },
                # Per-row widget button — navigates to the conversation holding
                # this row's source message. `action_name` resolves to the
                # `action_open_conversation` entry in `body.header.actions` above.
                {
                    "name": "row_actions",
                    "string": _("Actions"),
                    "widget": "buttons",
                    "editor": False,
                    "visible": True,
                    "width": 2,
                    "buttons": [
                        {
                            "string": _("Open Chat"),
                            "icon": "MessageSquare",
                            "color": "primary",
                            "size": "sm",
                            "border": True,
                            "fullColor": True,
                            "action_name": "action_open_conversation",
                        },
                    ],
                },
            ]
        },
    },
}


bank_roshtat_form_view = {
    "key": "drmagdy_bank_roshtat_form_view",
    "name": "Bank Roshtat Form View",
    "model": "drmagdy.bankroshtat",
    "menu_item": "drmagdy_main_menu_bank_roshtat",
    "view_type": "form",
    "priority": 10,
    "module": "drmagdy",
    "body": {
        # "Open Conversation" navigates to the chat holding the source message.
        # Hidden when there is no linked message (the field itself is hidden per
        # request, but its value still drives this visibility rule).
        "header": {
            "actions": [
                {
                    "name": "action_open_conversation",
                    "string": _("Open Conversation"),
                    "icon": "MessageSquare",
                    "type": "server",
                    "as": "button",
                    "variant": "primary",
                    "confirm_required": False,
                    "invisible": {"field": "message", "operator": "is_null"},
                },
            ],
        },
        "sheet": {
            "title": {
                "fields": [
                    {
                        "name": "name",
                        "string": _("Name"),
                        "widget": "text",
                        "required": True,
                        "readonly": False,
                        "help": _("Auto-generated from the chat message"),
                        "placeholder": _("Enter a name"),
                    }
                ]
            },
            "sections": [
                {
                    "title": "",
                    "groups": [
                        {
                            "fields": [
                                {
                                    "name": "attachment",
                                    "string": _("Image"),
                                    # `files` widget (single mode) instead of `image`:
                                    # it ships a click-to-open modal viewer/lightbox
                                    # that the `image` widget lacks.
                                    "widget": "files",
                                    "multiSelect": False,
                                    "accept": "image/*",
                                    "maxView": 1,
                                    "required": True,
                                    "readonly": False,
                                    "help": _("Prescription image — click to preview"),
                                },
                                # Source Message field intentionally hidden (per
                                # request). The linked message is still reachable
                                # via the "Open Conversation" header button above.
                                {
                                    "name": "created_at",
                                    "string": _("Created On"),
                                    "widget": "datetime",
                                    "required": False,
                                    "readonly": True,
                                    "help": _("Date and time this row was created"),
                                },
                            ]
                        }
                    ],
                }
            ],
            "tabs": [
                {
                    "title": _("Notes"),
                    "sections": [
                        {
                            "title": "",
                            "groups": [
                                {
                                    "fullWidth": True,
                                    "fields": [
                                        {
                                            "name": "notes",
                                            "string": "",
                                            "widget": "editor",
                                            "required": False,
                                            "readonly": False,
                                            "placeholder": _("Enter notes here"),
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    },
}
