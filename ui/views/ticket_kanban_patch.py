# -*- coding: utf-8 -*-
"""
drmagdy Module - Support Ticket Kanban View Patch.

Patches the support ticket kanban card (parent key:
``support_ticket_kanban_view``) via Odoo-style view inheritance:

  - a FIXED card structure, one kind of item per block, so every card lines
    up the same way (the header is a label-less flow-wrap: with five items of
    different widths every card broke the line somewhere else and the date or
    the category landed wherever there was room — 2026-09-24 complaint):
      header  : priority stars · assignee chip                 (who)
      body    : Category · <chip>                              (labelled row)
                <contact-status pill>                          (only when set)
      footer  : created date + time (left) ·
                Delivered | Cancelled · Late · Urgent pills    (right)
    ``body`` / ``footer`` are added to the card with a ``modify`` on the
    direct path ``kanban.card`` (dict update), ``created_at`` is removed
    from the header. ``created_at`` shows date + time (``datetime`` widget);
  - four state pills (``badge`` widget, solid fill, drawn ONLY when the flag
    is on — the widget skips an off flag, ``utils/values.ts`` ``isEmptyValue``):
      * green **Delivered** (``is_delivered``) / red **Cancelled**
        (``is_cancelled``): the order outcome (2026-09-27);
      * red **Late** (``is_late``): expected arrival passed, still under order;
      * amber **Urgent** (``is_urgent``): the pharmacy's مستعجل flag.
    All are readonly so they stay out of the quick-create form
    (``project/web/src/widgets/kanban/components/widgets/index.tsx``);
  - **Contact status** (``contact_status``, a choices column) as a coloured
    status pill in the body, one tone per value (``colors``). The kanban card
    schema does NOT expand model choices for card fields (``kanban_board.py``
    ``build_card_schema`` only rewrites relation widgets), so the ``options``
    are given here explicitly and MUST match ``choices.CONTACT_STATUS_CHOICES``
    — ``drmagdy/tests.py`` asserts it (and that every key has a tone). The
    pill is hidden on tickets with no status (empty-value policy);
  - **late tickets first** in every column, then newest first:
    ``body.kanban.order_by`` is the board's default card order
    (``modules/base/views/kanban_paginated_view.py``); a sort picked in the
    search bar still wins. The ``kanban`` selector resolves to the board's
    config block (``ui_view.py`` ``_is_element_type``), so the ``modify``
    lands on ``body.kanban`` and not on the body root. ``drmagdy/tests.py``
    applies these operations to the base body and asserts all of this.

``is_late`` is a real column on ``support_ticket`` (``TicketExtension``,
recomputed on save and by the arrival reminder task) because the filter engine
can only ORDER by columns — a Python property would show but never sort.

Labels (and the option labels) are plain English here and translated on the
card by the frontend catalogue (``gettext(field.string)`` / ``gettext(label)``),
like "Category" always was; every msgid used below already exists in the
extension's Arabic catalogue ("Late" = متأخر, the contact-status labels, ...).
The one exception is "Urgent": core modules translate that msgid as "عاجل"
and win the merge, so its label is a ``{"ar", "en"}`` dict, which the view
engine flattens to the active language before the card ever sees it.

Note: ``support.ticket`` has no ``type`` field; ``category`` (FK ->
``support.TicketCategory``) is the ticket's classification and is what we
surface as the "Type" on the card.
"""
from django.utils.translation import gettext as _


# Card options for contact_status: {stored key: label}. Keep in step with
# choices.CONTACT_STATUS_CHOICES (tests.py: test_contact_status_options_match_choices).
CONTACT_STATUS_CARD_OPTIONS = {
    "no_answer": _("No answer"),
    "contacted_waiting": _("Contacted, awaiting reply"),
    "contacted_will_pickup": _("Contacted, will pick up"),
    "delivered": _("Delivered"),
}

# Tone of the contact-status pill per stored key: red = nobody answered
# (follow up), amber = waiting on the customer, blue = coming to pick up,
# green = delivered.
CONTACT_STATUS_CARD_COLORS = {
    "no_answer": "danger",
    "contacted_waiting": "warning",
    "contacted_will_pickup": "info",
    "delivered": "success",
}


ticket_kanban_drmagdy_patch = {
    "key": "ticket_kanban_drmagdy_patch",
    "name": "Support Ticket Kanban - drmagdy order status, Late/Urgent pills, Contact status, Type, Datetime",
    "model": "support.ticket",
    "view_type": "kanban",
    "priority": 50,
    "inherit_mode": "extension",
    "inherit_id": "support_ticket_kanban_view",
    "module": "drmagdy",
    "inheritance_operations": [
        {
            # The date leaves the header flow (it moves to the footer below).
            "operation": "remove",
            "target": "field[name=created_at]",
        },
        {
            # Body + footer blocks (the base card has header only). Ticket
            # "Type" = category and the contact status, each a labelled row
            # of its own; the created date + time always last, label hidden —
            # a timestamp reads as a footer line, not as a value to compare.
            "operation": "modify",
            "target": "kanban.card",
            "content": {
                "body": {
                    "fields": [
                        {
                            "name": "category",
                            "tag": "field",
                            "widget": "relation",
                            "displayField": "name",
                            "multiSelect": False,
                            "required": False,
                            "readonly": True,
                            "string": _("Category"),
                        },
                        {
                            # Outcome of contacting the customer once the item
                            # arrived, as a status pill (owner's call
                            # 2026-09-27: "a status, not a normal field"). The
                            # badge maps key -> option label and key -> tone
                            # (`colors`); `color` is the tone for a value
                            # `colors` does not name. The phone icon says what
                            # the pill is about, since a badge draws no label.
                            # Hidden while unset, so cards before "اصناف
                            # وصلت" stay short.
                            "name": "contact_status",
                            "tag": "field",
                            "widget": "badge",
                            "options": CONTACT_STATUS_CARD_OPTIONS,
                            "colors": CONTACT_STATUS_CARD_COLORS,
                            "color": "info",
                            "icon": "PhoneCall",
                            "required": False,
                            "readonly": True,
                            "string": _("Contact status"),
                        },
                    ],
                },
                "footer": {
                    "left": [
                        {
                            "name": "created_at",
                            "tag": "field",
                            "widget": "datetime",
                            "required": False,
                            "readonly": True,
                            "hideLabel": True,
                            "string": _("Created On"),
                        },
                    ],
                    # State pills at the END of the last row, opposite the
                    # date (user's call 2026-09-24); the footer's empty policy
                    # hides each slot on tickets where the flag is off, and the
                    # whole side when both are. readonly keeps them out of the
                    # quick-create form. Late first: it outranks urgency on the
                    # form ribbon too (compute_ribbon_state).
                    "right": [
                        # Order outcome first (owner, 2026-09-27): green
                        # Delivered (the form's Delivered button) or red
                        # Cancelled (the Cancel Order wizard, item kept). The
                        # two never meet, and neither meets Late (late needs an
                        # open, uncancelled ticket). Bilingual labels: core
                        # catalogues translate "Cancelled" as "ملغاة".
                        {
                            "name": "is_delivered",
                            "tag": "field",
                            "widget": "badge",
                            "color": "success",
                            "icon": "PackageCheck",
                            "readonly": True,
                            "required": False,
                            "string": {"ar": "تم التسليم", "en": "Delivered"},
                        },
                        {
                            "name": "is_cancelled",
                            "tag": "field",
                            "widget": "badge",
                            "color": "danger",
                            "icon": "XCircle",
                            "readonly": True,
                            "required": False,
                            "string": {"ar": "ملغي", "en": "Cancelled"},
                        },
                        {
                            "name": "is_late",
                            "tag": "field",
                            "widget": "badge",
                            "color": "danger",
                            "icon": "Clock",
                            "readonly": True,
                            "required": False,
                            "string": _("Late"),
                        },
                        {
                            "name": "is_urgent",
                            "tag": "field",
                            "widget": "badge",
                            "color": "warning",
                            "icon": "Zap",
                            "readonly": True,
                            "required": False,
                            # Bilingual on purpose: four core modules translate
                            # the msgid "Urgent" as "عاجل" and outrank this
                            # extension in the merged catalogue; the engine
                            # flattens a {lang: str} label to the user's language
                            # (ui_view.get_view_data -> flatten_translations), so
                            # the pharmacy's word wins in both languages.
                            "string": {"ar": "مستعجل", "en": "Urgent"},
                        },
                    ],
                },
            },
        },
        {
            # Late tickets first in every column, then the model's own order
            # (newest first). Kanban only: the list keeps Meta.ordering.
            "operation": "modify",
            "target": "kanban",
            "content": {"order_by": ["-is_late", "-created_at"]},
        },
    ],
}
