# -*- coding: utf-8 -*-
# drmagdy - restrict the grouping "Configuration"-type parent menus to
# managers + admins only. Because each of these is a PARENT that groups
# other menu items, gating the parent hides its whole subtree from anyone
# who is not in the allowed groups.
#
# Rule (per request): allow [<module>.managers, <module>.admins]. If a
# module has no ".managers" group, fall back to ".admins" only.
#
# Group existence checked against each module's security/groups.py:
#   crm      -> crm.managers      + crm.admins        (both exist)
#   support  -> support.managers  + support.admins    (both exist)
#   projects -> projects.managers + projects.admins   (both exist)
#   contacts -> contacts.admins   ONLY  (no contacts.managers group defined)
#
# Each entry patches ONE base menu item via a `replace` op on its
# `allowed_groups` list. On sync, groups are resolved by technical_name.
from django.utils.translation import gettext as _


menu_dict = {
    # 1) CRM > Configuration
    "restrict_crm_config_to_managers": {
        "_inherit": "crm_main_menu_configuration",
        "inheritance_operations": [
            {
                "operation": "replace",
                "target": "allowed_groups",
                "content": ["crm.managers", "crm.admins"],
            },
        ],
    },
    # 2) Support (Tickets) > Configuration
    "restrict_support_config_to_managers": {
        "_inherit": "support_main_menu_configuration",
        "inheritance_operations": [
            {
                "operation": "replace",
                "target": "allowed_groups",
                "content": ["support.managers", "support.admins"],
            },
        ],
    },
    # 3) Projects > Configuration
    "restrict_projects_config_to_managers": {
        "_inherit": "projects_main_menu_configuration",
        "inheritance_operations": [
            {
                "operation": "replace",
                "target": "allowed_groups",
                "content": ["projects.managers", "projects.admins"],
            },
        ],
    },
    # 4a) Contacts > Features  (no contacts.managers group -> admins only)
    "restrict_contacts_features_to_admins": {
        "_inherit": "contacts_main_menu_features",
        "inheritance_operations": [
            {
                "operation": "replace",
                "target": "allowed_groups",
                "content": ["contacts.admins"],
            },
        ],
    },
    # 4b) Contacts > Countries  (no contacts.managers group -> admins only)
    "restrict_contacts_countries_to_admins": {
        "_inherit": "contacts_main_menu_features_country",
        "inheritance_operations": [
            {
                "operation": "replace",
                "target": "allowed_groups",
                "content": ["contacts.admins"],
            },
        ],
    },
    # 4c) Contacts > Banks  (no contacts.managers group -> admins only)
    "restrict_contacts_banks_to_admins": {
        "_inherit": "contacts_main_menu_features_bank",
        "inheritance_operations": [
            {
                "operation": "replace",
                "target": "allowed_groups",
                "content": ["contacts.admins"],
            },
        ],
    },
}
