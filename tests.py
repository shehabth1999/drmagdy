# -*- coding: utf-8 -*-
"""Guard tests for the drmagdy "items under order" ticket workflow.

The first test is the important one: it applies the ticket form patch to the
REAL base view body through the core inheritance engine and asserts the
result lands where the frontend reads it. The patch relies on the ``sheet``
selector resolving to the body root (see ``ui/views/ticket_form_patch.py``);
if core ever changes that, this test fails instead of the form silently
losing its fields and ribbon.

Run on a dev database: ``uv run python manage.py test drmagdy``.
"""
import copy
import importlib.util
import os
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from drmagdy import ticket_stages as st
from drmagdy.extensions import compute_is_late, compute_ribbon_state


def _load_view_module(relative_path):
    """Load a ui/views file the way the view registry does (by path)."""
    path = os.path.join(os.path.dirname(__file__), relative_path)
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _field_names(container):
    title = container.get("title")
    names = [f["name"] for f in title.get("fields", [])] if isinstance(title, dict) else []
    for section in container.get("sections", []):
        for group in section.get("groups", []):
            names += [f["name"] for f in group.get("fields", [])]
    for tab in container.get("tabs", []):
        names += _field_names(tab)
    return names


class TicketFormPatchTests(SimpleTestCase):
    def test_patch_lands_inside_the_sheet(self):
        from modules.base.models.ui_view import UIView
        from modules.support.ui.views.tickets import support_ticket_form_view

        patch = _load_view_module("ui/views/ticket_form_patch.py").ticket_form_drmagdy_patch
        body = copy.deepcopy(support_ticket_form_view["body"])
        result = UIView()._apply_inheritance_operations(body, patch["inheritance_operations"])

        self.assertNotIn("ribbon", result, "ribbon leaked to the body root: the sheet selector changed")
        self.assertEqual(result["sheet"]["ribbon"]["field_text"], "ribbon_state")
        names = _field_names(result["sheet"])
        for expected in ("name", "team", "supervisor", "files", "buyer", "supplier_code",
                         "expected_arrival_at", "contact_status", "ribbon_state"):
            self.assertIn(expected, names)
        actions = {a["name"] for a in result["header"]["actions"]}
        self.assertEqual(actions, {"action_send_ticket_image_to_conversations", "action_cancel_ticket"})

    def test_stage_conditions_cover_both_value_shapes(self):
        cond = st.stage_cond(st.PROCESSED)
        self.assertEqual([leaf["field"] for leaf in cond["or"]], ["stage.id", "stage"])
        cond = st.not_stage_cond(st.ARRIVED, st.PROCESSED)
        self.assertEqual(cond["and"][0]["value"], [st.ARRIVED, st.PROCESSED])


class RibbonStateTests(SimpleTestCase):
    def _ticket(self, **kwargs):
        base = dict(is_cancelled=False, is_returned=False, is_very_important=False,
                    is_urgent=False, expected_arrival_at=None, stage_id=st.UNDER_ORDER)
        base.update(kwargs)
        return SimpleNamespace(**base)

    def test_precedence(self):
        now = timezone.now()
        with mock.patch.object(st, "role_of", side_effect=lambda sid, cid=None: sid):
            self.assertIsNone(compute_ribbon_state(self._ticket(), now))
            self.assertEqual(compute_ribbon_state(self._ticket(is_urgent=True), now), "urgent")
            self.assertEqual(compute_ribbon_state(self._ticket(is_urgent=True, is_very_important=True), now), "very_important")
            self.assertEqual(compute_ribbon_state(self._ticket(is_very_important=True, is_returned=True), now), "returned")
            overdue = self._ticket(is_returned=True, expected_arrival_at=now - timedelta(minutes=1))
            self.assertEqual(compute_ribbon_state(overdue, now), "overdue")
            not_yet = self._ticket(expected_arrival_at=now + timedelta(hours=1))
            self.assertIsNone(compute_ribbon_state(not_yet, now))
            elsewhere = self._ticket(stage_id=st.ARRIVED, expected_arrival_at=now - timedelta(hours=1))
            self.assertIsNone(compute_ribbon_state(elsewhere, now))
            self.assertEqual(compute_ribbon_state(self._ticket(is_cancelled=True, expected_arrival_at=now - timedelta(hours=1)), now), "cancelled")


class IsLateTests(SimpleTestCase):
    """``is_late`` = due + still under order + not cancelled; the ribbon's
    "overdue" is the same predicate."""

    def _ticket(self, **kwargs):
        base = dict(is_cancelled=False, expected_arrival_at=None, stage_id=st.UNDER_ORDER)
        base.update(kwargs)
        return SimpleNamespace(**base)

    def test_late_only_while_due_under_order_and_not_cancelled(self):
        now = timezone.now()
        past, future = now - timedelta(minutes=1), now + timedelta(hours=1)
        with mock.patch.object(st, "role_of", side_effect=lambda sid, cid=None: sid):
            self.assertTrue(compute_is_late(self._ticket(expected_arrival_at=past), now))
            self.assertTrue(compute_is_late(self._ticket(expected_arrival_at=now), now))
            self.assertFalse(compute_is_late(self._ticket(), now))
            self.assertFalse(compute_is_late(self._ticket(expected_arrival_at=future), now))
            self.assertFalse(compute_is_late(self._ticket(expected_arrival_at=past, stage_id=st.ARRIVED), now))
            self.assertFalse(compute_is_late(self._ticket(expected_arrival_at=past, stage_id=st.PROCESSED), now))
            self.assertFalse(compute_is_late(self._ticket(expected_arrival_at=past, is_cancelled=True), now))

    def test_naive_datetime_is_compared_as_aware(self):
        import datetime
        with mock.patch.object(st, "role_of", side_effect=lambda sid, cid=None: sid):
            self.assertTrue(compute_is_late(self._ticket(expected_arrival_at=datetime.datetime(2000, 1, 1)), timezone.now()))


class TicketKanbanPatchTests(SimpleTestCase):
    """The kanban patch relies on two core features added 2026-09-24: the
    ``kanban`` selector (``ui_view.py`` ``_is_element_type``) and
    ``body.kanban.order_by`` (``kanban_paginated_view.py``). If either goes,
    the badge still shows but late tickets stop sorting first — this test
    turns that silent regression into a failure."""

    def _apply(self):
        from modules.base.models.ui_view import UIView
        from modules.support.ui.views.tickets import support_ticket_kanban_view

        patch = _load_view_module("ui/views/ticket_kanban_patch.py").ticket_kanban_drmagdy_patch
        body = copy.deepcopy(support_ticket_kanban_view["body"])
        return UIView()._apply_inheritance_operations(body, patch["inheritance_operations"])

    def test_late_badge_leads_the_header_fields(self):
        result = self._apply()
        fields = result["kanban"]["card"]["header"]["fields"]
        self.assertEqual(fields[0]["name"], "is_late")
        self.assertEqual(fields[0]["widget"], "badge")
        self.assertEqual(fields[0]["color"], "danger")
        names = [f["name"] for f in fields]
        self.assertEqual(names, ["is_late", "priority", "assigned_to", "category", "created_at"])

    def test_late_first_is_the_board_default_order(self):
        result = self._apply()
        self.assertNotIn("order_by", result, "order_by leaked to the body root: the `kanban` selector changed")
        self.assertEqual(result["kanban"].get("order_by"), ["-is_late", "-created_at"],
                         "body.kanban.order_by missing: the `kanban` selector is not resolved by core")


class KanbanDefaultOrderTests(SimpleTestCase):
    """``body.kanban.order_by`` orders the board queryset unless the request
    sorts itself; a bad declaration falls back to Meta.ordering. Core columns
    only: the test runner process does not attach extension fields, so
    ``is_late`` itself is covered by the DB test in TransitionRuleTests."""

    def _view(self, default_order):
        from modules.base.views.kanban_paginated_view import KanbanPaginatedView

        view = KanbanPaginatedView()
        view.request = SimpleNamespace(_kanban_ctx={"group_by": None, "default_order": list(default_order)})
        return view

    def test_default_order_applies_when_the_request_has_none(self):
        from modules.support.models import Ticket

        qs = self._view(["-priority", "-created_at"]).get_queryset(Ticket)
        self.assertEqual(tuple(qs.query.order_by), ("-priority", "-created_at"))

    def test_request_order_wins(self):
        from modules.support.models import Ticket

        qs = self._view(["-priority", "-created_at"]).get_queryset(Ticket, filters={"order_by": ["name"]})
        self.assertEqual(tuple(qs.query.order_by), ("name",))

    def test_unknown_field_is_ignored(self):
        from modules.support.models import Ticket

        qs = self._view(["-no_such_column"]).get_queryset(Ticket)
        self.assertEqual(tuple(qs.query.order_by), ())


class TransitionRuleTests(TestCase):
    """Needs a database: creates stages, a branch-less ticket and moves it."""

    @classmethod
    def setUpTestData(cls):
        from modules.support.models import TicketStage
        cls.stages = {}
        for role, name in st.STAGE_NAMES.items():
            cls.stages[role] = TicketStage.objects.create(name=name, sequence=role * 10)
        st.clear_cache()

    def _make_ticket(self, **kwargs):
        from modules.support.models import Ticket
        return Ticket.objects.create(name="test", stage=self.stages[st.NEW], **kwargs)

    def test_entering_under_order_requires_buyer_supplier_and_date(self):
        from django.core.exceptions import ValidationError
        ticket = self._make_ticket()
        ticket.stage = self.stages[st.UNDER_ORDER]
        with self.assertRaises(ValidationError):
            ticket.save()

    def test_entering_under_order_with_data_passes_and_arms_reminder(self):
        from modules.base.models.user import User
        buyer = User.objects.create_user(email="buyer@example.com", password="x")
        ticket = self._make_ticket(buyer=buyer, supplier_code="S-1",
                                   expected_arrival_at=timezone.now() + timedelta(days=1))
        ticket.arrival_notified_at = timezone.now()
        ticket.stage = self.stages[st.UNDER_ORDER]
        ticket.save()
        ticket.refresh_from_db()
        self.assertIsNone(ticket.arrival_notified_at)

    def test_closing_from_arrived_requires_contact_status(self):
        from django.core.exceptions import ValidationError
        ticket = self._make_ticket()
        ticket._skip_stage_rules = True
        ticket.stage = self.stages[st.ARRIVED]
        ticket.save()
        del ticket._skip_stage_rules
        ticket.stage = self.stages[st.PROCESSED]
        with self.assertRaises(ValidationError):
            ticket.save()
        ticket.contact_status = "delivered"
        ticket.save()
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.closed_at)

    def test_late_flag_follows_stage_and_date(self):
        from modules.base.models.user import User
        buyer = User.objects.create_user(email="buyer2@example.com", password="x")
        ticket = self._make_ticket(buyer=buyer, supplier_code="S-2",
                                   expected_arrival_at=timezone.now() - timedelta(hours=1))
        self.assertFalse(ticket.is_late)               # جديد: not under order yet
        ticket.stage = self.stages[st.UNDER_ORDER]
        ticket.save()
        ticket.refresh_from_db()
        self.assertTrue(ticket.is_late)
        self.assertEqual(ticket.ribbon_state, "overdue")
        ticket.expected_arrival_at = timezone.now() + timedelta(days=1)
        ticket.save()
        ticket.refresh_from_db()
        self.assertFalse(ticket.is_late)               # date pushed out
        self.assertIsNone(ticket.ribbon_state)
        ticket.expected_arrival_at = timezone.now() - timedelta(hours=1)
        ticket.save()
        ticket.refresh_from_db()
        self.assertTrue(ticket.is_late)
        ticket._skip_stage_rules = True
        ticket.stage = self.stages[st.ARRIVED]
        ticket.save()
        ticket.refresh_from_db()
        self.assertFalse(ticket.is_late)               # arrived: no longer late

    def test_naive_expected_arrival_from_form_is_accepted(self):
        """The browser posts datetimes without a timezone; comparing them with
        timezone.now() used to raise "can't compare offset-naive and offset-aware
        datetimes" inside compute_ribbon_state."""
        import datetime
        ticket = self._make_ticket()
        ticket.expected_arrival_at = datetime.datetime(2030, 1, 1, 10, 0)  # naive
        ticket.save()
        ticket.refresh_from_db()
        self.assertTrue(timezone.is_aware(ticket.expected_arrival_at))
