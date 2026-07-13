# -*- coding: utf-8 -*-
# drmagdy - patch the chat MESSAGE actions menu (message_actions_menu_item)
# to add a "Mark Lead Won (Receipt)" server action.
#
# The handler lives on MessageExtension(_inherit='chat.message') in
# drmagdy/extensions.py as @action action_lead_won_from_receipt.
from django.utils.translation import gettext as _


menu_dict = {
    "drmagdy_message_actions_won_receipt": {
        "_inherit": "message_actions_menu_item",
        "inheritance_operations": [
            {
                "operation": "append",
                "target": "actions",
                "content": {
                    # MUST match the @action method name exactly.
                    "name": "action_lead_won_from_receipt",
                    "string": _("Mark Lead Won (Receipt)"),
                    "icon": "Trophy",
                    "type": "server",
                    "as": "button",
                    "variant": "success",
                    "selection_required": True,
                    "confirm_required": True,
                    # Show ONLY when exactly one message is selected AND it is an
                    # image. The button hides if ANY selected message makes
                    # invisible=true, so: hide when count > 1 OR type != image.
                    "invisible": {
                        "or": [
                            {"field": "_selected_count", "operator": "gt", "value": 1},
                            {"field": "type", "operator": "ne", "value": "image"},
                        ]
                    },
                },
            },
            {
                "operation": "append",
                "target": "actions",
                "content": {
                    # MUST match the @action method name exactly.
                    "name": "action_create_ticket_from_message",
                    "string": _("Create Ticket"),
                    "icon": "Ticket",
                    "type": "server",
                    "as": "button",
                    "variant": "primary",
                    "selection_required": True,
                    "confirm_required": False,
                    # Show ONLY for a single text or image message. Hide when more
                    # than one selected OR the message is neither text nor image.
                    "invisible": {
                        "or": [
                            {"field": "_selected_count", "operator": "gt", "value": 1},
                            {"field": "type", "operator": "not_in", "value": ["text", "image"]},
                        ]
                    },
                },
            },
            {
                "operation": "append",
                "target": "actions",
                "content": {
                    # MUST match the @action method name exactly.
                    "name": "action_create_bank_roshtat_from_message",
                    "string": _("Save to Bank Roshtat"),
                    "icon": "FileImage",
                    "type": "server",
                    "as": "button",
                    "variant": "secondary",
                    "selection_required": True,
                    "confirm_required": False,
                    # IMAGES ONLY. Show only when exactly one image message is
                    # selected. Hide when count > 1 OR type != image.
                    "invisible": {
                        "or": [
                            {"field": "_selected_count", "operator": "gt", "value": 1},
                            {"field": "type", "operator": "ne", "value": "image"},
                        ]
                    },
                },
            },
        ],
    }
}
