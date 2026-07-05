# -*- coding: utf-8 -*-
"""drmagdy runtime patches, applied from apps.ready().

Keeps drmagdy-specific behavior out of the shared core modules.
"""
import logging

logger = logging.getLogger(__name__)

_PATCHED = False


def apply_patches():
    global _PATCHED
    if _PATCHED:
        return
    from modules.base.models.access_conditions import AccessCondition

    _orig_apply_all = AccessCondition.apply_all_conditions

    @classmethod
    def apply_all_conditions(cls, queryset, model_name, permission_type="view", user=None):
        # drmagdy: support tickets are a SHARED queue — every user may read / create /
        # edit / (attempt to) delete ANY ticket, not just the ones assigned to them.
        # So we fully bypass the support "my tickets only" record rule; WHO can delete
        # is then governed purely by the delete_ticket model permission (admins only).
        if model_name == "support.ticket":
            return queryset
        return _orig_apply_all(queryset, model_name, permission_type, user)

    AccessCondition.apply_all_conditions = apply_all_conditions
    _PATCHED = True
    logger.info("drmagdy: support.ticket VIEW unscoped (all users see all tickets)")
