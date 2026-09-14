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
from drmagdy.extensions import compute_ribbon_state


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
