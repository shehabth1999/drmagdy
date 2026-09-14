# -*- coding: utf-8 -*-
"""
drmagdy Module - Support Ticket Form View Patch ("items under order" workflow).

Patches the base support ticket form (key ``support_supportticket_form_view``)
with the pharmacy layout:

  * the whole ``sheet`` is RESTATED (base fields verbatim + drmagdy fields +
    stage-driven visibility/readonly rules + ribbon);
  * ``Send to WhatsApp`` and ``Cancel Order`` are appended to ``header.actions``.

Why the sheet is restated instead of injected field by field
-------------------------------------------------------------
The view-inheritance engine (``modules/base/models/ui_view.py``,
``_is_element_type``) resolves the selector ``sheet`` to the element that
CONTAINS a ``sheet`` key — i.e. the body root — so a ``modify`` with
``content={"ribbon": ...}`` would land at ``body.ribbon``, which nothing reads.
The only inheritance-based way to put a ``ribbon`` inside the sheet is a
``modify`` on ``sheet`` whose content is ``{"sheet": <full sheet>}``: the root
gets its ``sheet`` key replaced wholesale. That is what operation 1 does.
``drmagdy/tests.py`` applies the operations to the base body and asserts the
ribbon and fields end up under ``body["sheet"]`` — if core ever changes the
selector, that test (and smoke test 1 of the runbook) fails loudly.

Stage-driven rules
------------------
Frontend ``required`` is boolean-only, so "required in stage X" is enforced
server-side (``TicketExtension.pre_save``); here we only show / hide / lock.
The header status value is ``{"id": N}`` after load and a bare ``N`` after a
pill click, hence every stage condition is built with the dual-shape helpers in
``drmagdy/ticket_stages.py`` (ids verified against production 2026-09-14).
"""
from django.utils.translation import gettext as _

from drmagdy.ticket_stages import (
    ARRIVED,
    PROCESSED,
    any_of,
    not_stage_cond,
    stage_leaves,
)


IS_CANCELLED = {"field": "is_cancelled", "operator": "eq", "value": True}

# Order fields are frozen once the ticket is processed or cancelled.
LOCKED = any_of(*stage_leaves([PROCESSED], "in"), IS_CANCELLED)


DRMAGDY_TICKET_SHEET = {
    "title": {
        "fields": [
            {
                "name": "name",
                "string": _("Ticket Subject"),
                "widget": "text",
                "required": True,
                "readonly": False,
                "help": _("Brief summary of the support issue"),
                "placeholder": _("Enter ticket subject"),
            }
        ]
    },
    # Diagonal banner driven by the server-maintained ``ribbon_state`` field
    # (choices → labels via the backend display_mapping). Hidden when empty.
    "ribbon": {
        "field_text": "ribbon_state",
        "color": {
            "danger": ["cancelled", "overdue"],
            "warning": ["returned"],
            "info": ["very_important"],
            "primary": ["urgent"],
        },
        "invisible": {"field": "ribbon_state", "operator": "is_null"},
    },
    "sections": [
        # ---- Section 1: base ticket fields (verbatim) + supervisor + files ----
        {
            "title": "",
            "groups": [
                {
                    "fields": [
                        {
                            "name": "team",
                            "string": _("Support Team"),
                            "widget": "relation",
                            "required": False,
                            "readonly": False,
                            "help": _("Team responsible for this ticket"),
                            "placeholder": _("Search..."),
                            "multiSelect": False,
                            "domain": {'is_active': True},
                            "context": {},
                        },
                        {
                            "name": "assigned_to",
                            "string": _("Assigned To"),
                            "widget": "relation",
                            "required": False,
                            "readonly": False,
                            "help": _("User assigned to handle this ticket"),
                            "placeholder": _("Search..."),
                            "multiSelect": False,
                            "domain": "",
                            "context": {},
                        },
                        {
                            "name": "supervisor",
                            "string": _("Supervisor"),
                            "widget": "relation",
                            "displayField": "name",
                            "multiSelect": False,
                            "required": False,
                            "readonly": False,
                            "placeholder": _("Select supervisor..."),
                            "help": _("Supervisor responsible for this ticket"),
                        },
                        {
                            "name": "partner",
                            "displayName": "name",
                            "string": _("Customer"),
                            "widget": "relation",
                            "required": False,
                            "readonly": False,
                            "help": _("Customer who submitted this ticket"),
                            "placeholder": _("Search..."),
                            "multiSelect": False,
                            "domain": "",
                            "context": {},
                        },
                        {
                            "name": "phone",
                            "string": _("Phone"),
                            "widget": "text",
                            "required": False,
                            "readonly": False,
                            "help": _("phone of custmer"),
                            "placeholder": _("Enter phone number"),
                        },
                        {
                            "name": "email",
                            "string": _("customer Email"),
                            "widget": "email",
                            "required": False,
                            "readonly": False,
                            "help": _("Email address of the customer person"),
                            "placeholder": _("Enter customer email"),
                        },
                        {
                            "name": "files",
                            "widget": "files",
                            "multiSelect": True,
                            "accept": "image/*",
                            "string": _("Files"),
                            "required": False,
                            "readonly": False,
                            "help": _("Images attached to this ticket"),
                        },
                    ]
                },
                {
                    "title": "",
                    "fields": [
                        {
                            "name": "category",
                            "string": _("Category"),
                            "widget": "relation",
                            "required": False,
                            "readonly": False,
                            "onChange": True,
                            "help": _("Category of the ticket"),
                            "placeholder": _("Search..."),
                            "multiSelect": False,
                            "domain": {'is_active': True},
                            "context": {},
                        },
                        {
                            "name": "priority",
                            "string": _("Priority"),
                            "widget": "starsRating",
                            "defaultValue": 1,
                            "required": False,
                            "readonly": False,
                            "help": _("Priority level of the ticket"),
                            "placeholder": _("Search..."),
                            "domain": "",
                            "context": {},
                        },
                        {
                            "name": "tags",
                            "string": _("Tags"),
                            "widget": "relation",
                            "required": False,
                            "readonly": False,
                            "help": _("Tags for categorizing this ticket"),
                            "placeholder": _("Add tags..."),
                            "multiSelect": True,
                            "domain": "",
                            "context": {},
                        },
                        {
                            "name": "created_at",
                            "string": _("Created On"),
                            "widget": "datetime",
                            "required": False,
                            "readonly": True,
                            "help": _("Date and time when this ticket was created"),
                            "placeholder": "",
                        },
                        {
                            "name": "closed_at",
                            "string": _("Closed On"),
                            "widget": "datetime",
                            "required": False,
                            "readonly": True,
                            "help": _("Date and time when this ticket was closed"),
                            "placeholder": "",
                        },
                        {
                            "name": "category_description",
                            "string": _("Category Description"),
                            "widget": "textarea",
                            "required": False,
                            "readonly": True,
                            "help": _("Description of the selected category"),
                            "placeholder": "",
                        },
                    ]
                },
            ],
        },
        # ---- Section 2: the pharmacy order data ----
        {
            "title": _("Order Details"),
            "groups": [
                {
                    "fields": [
                        {
                            "name": "buyer",
                            "string": _("Buyer"),
                            "widget": "relation",
                            "displayField": "name",
                            "multiSelect": False,
                            "required": False,
                            "readonly": LOCKED,
                            "placeholder": _("Who buys this order..."),
                            "help": _("Mandatory before moving the ticket to \"اصناف تحت الطلب\""),
                            "domain": {
                                "filters": {
                                    "operator": "and",
                                    "filters": [
                                        {"field": "is_active", "operator": "eq", "value": True},
                                        {"field": "ai_agent", "operator": "eq", "value": False},
                                    ],
                                }
                            },
                            "context": {},
                        },
                        {
                            "name": "supplier_code",
                            "string": _("Supplier code"),
                            "widget": "text",
                            "maxLength": 64,
                            "required": False,
                            "readonly": LOCKED,
                            "placeholder": _("Enter supplier code"),
                            "help": _("Mandatory before moving the ticket to \"اصناف تحت الطلب\""),
                        },
                        {
                            "name": "expected_arrival_at",
                            "string": _("Expected arrival"),
                            "widget": "datetime",
                            "required": False,
                            "readonly": LOCKED,
                            "help": _("When the ordered item should arrive. Mandatory before moving to \"اصناف تحت الطلب\"; online users are alerted once it passes while the ticket is still there."),
                        },
                    ]
                },
                {
                    "fields": [
                        {
                            "name": "is_urgent",
                            "string": _("Urgent"),
                            "widget": "switch",
                            "required": False,
                            "readonly": LOCKED,
                            "help": _("Off = normal (عادي), on = urgent (مستعجل)"),
                        },
                        {
                            "name": "is_very_important",
                            "string": _("Very important — obtain from anywhere"),
                            "widget": "switch",
                            "required": False,
                            "readonly": LOCKED,
                            "help": _("The order must be obtained from any source because of its importance"),
                        },
                        {
                            "name": "contact_status",
                            "string": _("Contact status"),
                            "widget": "select",
                            "required": False,
                            # Only meaningful once the item has arrived (and kept visible after closing).
                            "invisible": not_stage_cond(ARRIVED, PROCESSED),
                            "readonly": LOCKED,
                            "help": _("Result of contacting the customer. Mandatory before closing from \"اصناف وصلت\""),
                        },
                        # Hidden, server-maintained fields. They must be part of
                        # the form schema so the record payload carries them (the
                        # ribbon and the conditions above read them).
                        {"name": "ribbon_state", "string": _("Ribbon"), "widget": "select", "invisible": True, "readonly": True},
                        {"name": "is_cancelled", "string": _("Cancelled"), "widget": "switch", "invisible": True, "readonly": True},
                        {"name": "is_returned", "string": _("Returned"), "widget": "switch", "invisible": True, "readonly": True},
                    ]
                },
            ],
        },
    ],
    "tabs": [
        {
            "title": _("Note"),
            "sections": [
                {
                    "title": "",
                    "groups": [
                        {
                            "fullWidth": True,
                            "fields": [
                                {
                                    "name": "description",
                                    "string": "",
                                    "widget": "editor",
                                    "required": False,
                                    "readonly": False,
                                    "placeholder": _("Enter Notes here"),
                                },
                            ]
                        }
                    ]
                }
            ]
        },
        {
            "title": _("Cancellation / Return"),
            # Only shown once the cancel wizard touched the ticket.
            "invisible": {"and": [
                {"field": "is_cancelled", "operator": "ne", "value": True},
                {"field": "is_returned", "operator": "ne", "value": True},
            ]},
            "sections": [
                {
                    "title": "",
                    "groups": [
                        {
                            "fields": [
                                {"name": "cancel_mode", "string": _("Outcome"), "widget": "select", "readonly": True},
                                {"name": "cancelled_at", "string": _("Cancelled / returned on"), "widget": "datetime", "readonly": True},
                                {"name": "return_count", "string": _("Times returned"), "widget": "number", "readonly": True},
                            ]
                        },
                        {
                            "fullWidth": True,
                            "fields": [
                                {"name": "cancel_reason", "string": _("Reason"), "widget": "textarea", "rows": 3, "readonly": True},
                            ]
                        },
                    ]
                }
            ]
        },
    ],
}


# ---------------------------------------------------------------------------
# Translations for PATCH content.
# The view registry pre-translates strings into {lang: text} dicts at sync time,
# but only for a view's ``body`` (view_registry.py: ``_expand_translations`` is
# applied to ``view_dict_copy['body']``), never for ``inheritance_operations``.
# Patched labels would therefore reach the browser in English. We run the same
# expansion here, with the same key set, lookup chain (pgettext with this file
# as context → module gettext → Django catalogue → source) and language list.
# ---------------------------------------------------------------------------
import gettext as _gettext_module
from pathlib import Path as _Path

from django.conf import settings as _settings

try:
    from modules.base.registry.i18n_utils import VIEW_TRANSLATABLE_KEYS as _KEYS, catalog_gettext as _catalog_gettext
except Exception:  # pragma: no cover - keep the patch importable if core moves
    _KEYS = frozenset({"string", "placeholder", "help", "title", "label", "confirm_message"})

    def _catalog_gettext(lang, message):
        return message

_SOURCE_FILE = "ui/views/ticket_form_patch.py"
_LOCALE_DIR = _Path(__file__).resolve().parents[2] / "locale"


def _languages():
    """Same source as ViewRegistry.languages: active, translatable Language rows."""
    try:
        from modules.base.models.country import Language

        langs = list(Language.objects.filter(active=True, translatable=True).values_list("iso_code", flat=True))
        if langs:
            return langs
    except Exception:  # pragma: no cover - table missing during early migrations
        pass
    return [code for code, _name in getattr(_settings, "LANGUAGES", (("en", "English"),))]


def _translators(langs):
    out = {}
    for lang in langs:
        try:
            out[lang] = _gettext_module.translation("django", localedir=str(_LOCALE_DIR), languages=[lang])
        except FileNotFoundError:
            out[lang] = None
    return out


def _expand_translations(node, langs, translators):
    if isinstance(node, dict):
        result = {}
        for k, v in node.items():
            if k in _KEYS and isinstance(v, str) and v:
                translations = {}
                for lang in langs:
                    translated = None
                    module_t = translators.get(lang)
                    if module_t:
                        t = module_t.pgettext(_SOURCE_FILE, v)
                        if t and t != v:
                            translated = t
                        if not translated:
                            t = module_t.gettext(v)
                            if t and t != v:
                                translated = t
                    if not translated:
                        t = _catalog_gettext(lang, v)
                        if t and t != v:
                            translated = t
                    translations[lang] = translated or v
                result[k] = translations
            else:
                result[k] = _expand_translations(v, langs, translators)
        return result
    if isinstance(node, list):
        return [_expand_translations(item, langs, translators) for item in node]
    return node


ticket_form_drmagdy_patch = {
    "key": "ticket_form_drmagdy_patch",
    "name": "Support Ticket Form - drmagdy items under order",
    "model": "support.ticket",
    "view_type": "form",
    "priority": 50,
    "inherit_mode": "extension",
    "inherit_id": "support_supportticket_form_view",
    "module": "drmagdy",
    "inheritance_operations": [
        # 1) Restate the whole sheet (see module docstring for why).
        {
            "operation": "modify",
            "target": "sheet",
            "content": {"sheet": DRMAGDY_TICKET_SHEET},
        },
        # 2) Menu-type action: opens the SendTicketImageAction wizard (slideover)
        # to send this ticket's image to WhatsApp conversations. Handler:
        # Ticket.action_send_ticket_image_to_conversations(queryset, form)
        # (TicketExtension, drmagdy/extensions.py). Hidden when the ticket has
        # no image.
        {
            "operation": "append",
            "target": "header.actions",
            "content": [
                {
                    "name": "action_send_ticket_image_to_conversations",
                    "string": _("Send to WhatsApp"),
                    "icon": "Send",
                    "type": "menu",
                    "as": "button",
                    "variant": "success",
                    "view_key": "drmagdy_send_ticket_image_form_view",
                    "menu_type": "slideover",
                    "view_type": ["form"],
                    # Managers + admins only (admins imply managers; superusers
                    # bypass). Enforced server-side too, in the @action handler.
                    "allowed_groups": ["support.managers"],
                    # Hide when the ticket has no images. `files` is an M2M so an
                    # empty value serializes as [] (not null): is_null alone won't
                    # match. String([]) === "" in JS, so eq "" hides on an empty
                    # array; the is_null branch also covers a null value.
                    "invisible": {"or": [
                        {"field": "files", "operator": "is_null"},
                        {"field": "files", "operator": "eq", "value": ""},
                    ]},
                },
            ],
        },
        # 3) Menu-type action: opens the CancelTicketAction wizard (slideover).
        # Handler: Ticket.action_cancel_ticket(queryset, form). Hidden once the
        # ticket is processed or already cancelled.
        {
            "operation": "append",
            "target": "header.actions",
            "content": [
                {
                    "name": "action_cancel_ticket",
                    "string": _("Cancel Order"),
                    "icon": "XCircle",
                    "type": "menu",
                    "as": "button",
                    "variant": "danger",
                    "view_key": "drmagdy_cancel_ticket_form_view",
                    "menu_type": "slideover",
                    "view_type": ["form"],
                    "on_success": {"type": "refresh"},
                    "invisible": any_of(*stage_leaves([PROCESSED], "in"), IS_CANCELLED),
                },
            ],
        },
    ],
}

# Pre-translate every label in the operations (see the block above).
_langs = _languages()
ticket_form_drmagdy_patch["inheritance_operations"] = _expand_translations(
    ticket_form_drmagdy_patch["inheritance_operations"], _langs, _translators(_langs)
)
