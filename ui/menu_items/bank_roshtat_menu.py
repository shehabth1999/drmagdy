# -*- coding: utf-8 -*-
# drmagdy - top-level menu holding the "Bank Roshtat" (prescription bank) views.
# The `action_create_bank_roshtat_from_message` server action opens the created
# row via this menu item's key (`drmagdy_main_menu_bank_roshtat`).
from django.utils.translation import gettext as _


menu_dict = {
    "drmagdy_main_menu": {
        "name": _("Dr Magdy"),
        "icon": "Stethoscope",  # lucide icon
        "module": "drmagdy",
        "sequence": 25,
        "allowed_groups": ["drmagdy.users"],
        "children": {
            "drmagdy_main_menu_bank_roshtat": {
                "model": "drmagdy.bankroshtat",
                "sequence": 10,
                "name": _("Bank Roshtat"),
                "view_types": "list,form",
                "icon": "FileImage",
                "module": "drmagdy",
                "allowed_groups": ["drmagdy.users"],
            },
        },
    }
}
