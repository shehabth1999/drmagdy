# -*- coding: utf-8 -*-
"""Ticket-stage knowledge for the drmagdy "items under order" workflow.

The support module keeps stages as DATA (support.TicketStage rows), so this
module is the single place that maps the pharmacy's workflow roles onto the
live rows:

* Form-view conditions (frontend) can only compare the raw stage id, so the
  constants below are the ids as they exist in the production database
  (verified 2026-09-14). ``stage_cond`` / ``not_stage_cond`` build conditions
  that work for BOTH value shapes the form produces for the header status
  field: ``{"id": N}`` right after load and a bare ``N`` after a status-pill
  click or in create mode.
* Backend logic must go through ``stage_id()`` / ``role_of()``: they use the
  constant id when that row still exists and fall back to matching the stage
  NAME (logging a warning) so a recreated stage degrades gracefully instead of
  silently disabling the rules.

If the pharmacy ever recreates its stages, update the ids here and re-run
``sync_ui_views`` so the form conditions follow.
"""
import logging

from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# --- Live stage ids (support_ticketstage, company 1) -------------------------
NEW = 4            # جديد
IN_PROGRESS = 7    # جاري التعامل   (row carries is_closed=True by mistake — never key on is_closed)
UNAVAILABLE = 10   # اصناف غير متوفرة
UNDER_ORDER = 8    # اصناف تحت الطلب
ARRIVED = 9        # اصناف وصلت
PROCESSED = 6      # تمت المعالجة

STAGE_NAMES = {
    NEW: "جديد",
    IN_PROGRESS: "جاري التعامل",
    UNAVAILABLE: "اصناف غير متوفرة",
    UNDER_ORDER: "اصناف تحت الطلب",
    ARRIVED: "اصناف وصلت",
    PROCESSED: "تمت المعالجة",
}
ROLES = tuple(STAGE_NAMES)

# Stages that count as "closed" for closed_at bookkeeping and read-only rules.
CLOSED = (PROCESSED,)

CACHE_TIMEOUT = 60 * 60  # 1 hour


# --- Frontend condition helpers ----------------------------------------------
def stage_leaves(ids, operator):
    """The two leaf conditions that together cover both status value shapes."""
    ids = list(ids)
    return [
        {"field": "stage.id", "operator": operator, "value": ids},
        {"field": "stage", "operator": operator, "value": ids},
    ]


def stage_cond(*ids):
    """Condition that is TRUE when the ticket's stage is one of ``ids``.

    ``in`` against an unresolvable path is false, so exactly one leaf decides
    for either value shape.
    """
    return {"or": stage_leaves(ids, "in")}


def not_stage_cond(*ids):
    """Condition that is TRUE when the stage is NOT one of ``ids`` (or unset).

    ``not_in`` against an unresolvable path is true, so again exactly one leaf
    decides for either value shape; both must agree, hence ``and``.
    """
    return {"and": stage_leaves(ids, "not_in")}


def any_of(*leaves):
    """Flat ``or`` over leaf conditions (avoids nesting compound conditions)."""
    return {"or": list(leaves)}


# --- Transition rules (enforced server-side in TicketExtension.pre_save) ------
# Master switch. Must only be True once the form view that exposes the required
# fields (ui/views/ticket_form_patch.py) is deployed, otherwise users are blocked
# from moving tickets with no way to fill the fields.
ENFORCE_STAGE_RULES = True

# role entered -> fields that must be filled. ``required_from`` restricts the
# rule to a specific previous stage. Labels are what the blocking message shows.
TRANSITION_RULES = {
    UNDER_ORDER: {
        "required": {
            "buyer": _("Buyer"),
            "expected_arrival_at": _("Expected arrival"),
            "supplier_code": _("Supplier code"),
        },
    },
    PROCESSED: {
        "required_from": {
            ARRIVED: {"contact_status": _("Contact status")},
        },
    },
}


# --- Backend resolution -------------------------------------------------------
def _cache_key(role, company_id):
    return f"drmagdy:ticket_stage:{role}:{company_id or 0}"


def stage_id(role, company_id=None):
    """Return the live TicketStage id for a workflow role (cached 1 hour).

    Prefers the constant id when that row still exists; otherwise matches the
    stage name (exact, then contains, case-insensitive) and warns so the
    constants get updated. Returns ``None`` (uncached) when nothing matches.
    """
    if role not in STAGE_NAMES:
        raise ValueError(f"Unknown ticket stage role: {role!r}")

    key = _cache_key(role, company_id)
    hit = cache.get(key)
    if hit is not None:
        return hit

    from modules.support.models import TicketStage

    qs = TicketStage.all_objects.all()
    if company_id:
        qs = qs.filter(company_id=company_id)

    resolved = None
    if qs.filter(pk=role).exists():
        resolved = role
    else:
        name = STAGE_NAMES[role].strip()
        resolved = (
            qs.filter(name__iexact=name).order_by("sequence", "id").values_list("id", flat=True).first()
            or qs.filter(name__icontains=name).order_by("sequence", "id").values_list("id", flat=True).first()
        )
        if resolved is not None:
            logger.warning(
                "drmagdy: ticket stage %r (expected id %s) resolved by NAME to id %s; "
                "update ticket_stages.py and re-sync the form view conditions.",
                name, role, resolved,
            )
        else:
            logger.warning("drmagdy: ticket stage %r (id %s) not found; stage rules for it are disabled.", name, role)

    if resolved is not None:
        cache.set(key, resolved, CACHE_TIMEOUT)
    return resolved


def role_of(live_stage_id, company_id=None):
    """Map a live TicketStage id back to its workflow role, or ``None``."""
    if not live_stage_id:
        return None
    for role in ROLES:
        if stage_id(role, company_id) == live_stage_id:
            return role
    return None


def clear_cache(company_id=None):
    for role in ROLES:
        cache.delete(_cache_key(role, company_id))
