# -*- coding: utf-8 -*-
# drmagdy: hide the "Sales Orders" button (action name: get_sales_orders) that the
# `sales` module appends to the chat conversation menu (chat_main_menu_omnichannel).
# priority > 10 so this remove runs AFTER sales' append (which is default priority 10).
menu_dict = {
    "drmagdy_hide_sales_order_action_omnichannel": {
        "_inherit": "chat_main_menu_omnichannel",
        "priority": 50,
        "inheritance_operations": [
            {
                "operation": "remove",
                "target": "actions",
                "match": {"name": "get_sales_orders"},
            },
        ],
    }
}
