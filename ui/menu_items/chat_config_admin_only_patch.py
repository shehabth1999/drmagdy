# -*- coding: utf-8 -*-
# drmagdy - restrict the chat "Config" submenu items to admins only.
#
# Gates Tags / Teams / Groups (all under chat > Config) to the chat.admins
# group, so regular chat.users no longer see them. The "Config" parent and
# "Quick Replies" are left untouched, so agents still reach Quick Replies.
#
# Each entry patches ONE base menu item (from the chat module) via a
# `replace` op on its `allowed_groups` list. On sync, allowed_groups is
# resolved by group technical_name -> only members (and superusers) see it.
from django.utils.translation import gettext as _


menu_dict = {
    "restrict_chat_tags_to_admins": {
        "_inherit": "chat_main_menu_omnichannel_tags",
        "inheritance_operations": [
            {
                "operation": "replace",
                "target": "allowed_groups",
                "content": ["chat.admins"],
            },
        ],
    },
    "restrict_chat_teams_to_admins": {
        "_inherit": "chat_main_menu_omnichannel_teams",
        "inheritance_operations": [
            {
                "operation": "replace",
                "target": "allowed_groups",
                "content": ["chat.admins"],
            },
        ],
    },
    "restrict_chat_groups_to_admins": {
        "_inherit": "chat_main_menu_omnichannel_campaigns",
        "inheritance_operations": [
            {
                "operation": "replace",
                "target": "allowed_groups",
                "content": ["chat.admins"],
            },
        ],
    },
}
