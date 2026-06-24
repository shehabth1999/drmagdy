# -*- coding: utf-8 -*-
"""
Security groups for drmagdy module

This file defines all security groups for the drmagdy module.
Groups are synced to the database using the sync_groups management command.
"""

GROUPS = [
    {
        'name': 'Drmagdy Users',
        'technical_name': 'drmagdy.users',
        'category': 'Drmagdy',
        'description': 'Access drmagdy module',
    },
    {
        'name': 'Drmagdy Admins',
        'technical_name': 'drmagdy.admins',
        'category': 'Drmagdy',
        'implied_groups': ['drmagdy.users'],
        'description': 'Manage all drmagdy module',
    }
]
