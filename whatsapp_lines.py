# -*- coding: utf-8 -*-
"""WhatsApp "lines" of the "Send Ticket Image" wizard.

A line is one connected number the wizard can send from: a WhatsApp API
account (``whatsapp.whatsappaccount``) or a WhatsApp Web connection
(``wa_web.wawebaccount``). A relation field can only point at ONE model and
the wizard's dropdown has to list both, so the pick is stored as one string,
``"<kind>:<account id>"`` (``"wa_web:1"``, ``"whatsapp:3"``), in
``SendTicketImageAction.whatsapp_line``. The kind is also the
``Conversation.type`` of the chats on that line.

Used by the wizard view (dropdown options, default line and the Customers
domain are computed when the view is synced), by both registrations of the
wizard's ``@onchange`` and by the send handler.
"""
from django.apps import apps

API = "whatsapp"
WEB = "wa_web"

# kind -> (app label, model name) of the account behind a line.
LINE_MODELS = {
    API: ("whatsapp", "whatsappaccount"),
    WEB: ("wa_web", "wawebaccount"),
}

CHANNEL_NAMES = {API: "WhatsApp API", WEB: "WhatsApp Web"}

# The wizard opens on the number of this API account (matched by NAME, so a
# re-created account row still matches) — through its WhatsApp Web connection
# when the number has one.
DEFAULT_ACCOUNT_NAME = "Admin Pharmacy"


def _account_model(kind):
    """Account model of a kind; None when that channel is not installed."""
    try:
        return apps.get_model(*LINE_MODELS[kind])
    except (KeyError, LookupError):
        return None


def line_key(kind, account_id):
    return f"{kind}:{account_id}"


def parse_line(value):
    """``("wa_web", 1)`` from ``"wa_web:1"``; None for anything else."""
    kind, _sep, raw_id = str(value or "").partition(":")
    if kind not in LINE_MODELS or not raw_id.isdigit():
        return None
    return kind, int(raw_id)


def get_line_account(value):
    """``(kind, account)`` of the ACTIVE account behind a line, else ``(None, None)``."""
    parsed = parse_line(value)
    if parsed is None:
        return None, None
    kind, account_id = parsed
    model = _account_model(kind)
    account = model._base_manager.filter(pk=account_id, active=True).first() if model else None
    return (kind, account) if account else (None, None)


def line_label(kind, account):
    """Dropdown label: ``pharmacy admin web — WhatsApp Web (+201158039596)``."""
    name = (account.name or "").strip() or CHANNEL_NAMES[kind]
    label = f"{name} — {CHANNEL_NAMES[kind]}"
    if account.phone_number:
        label += f" (+{str(account.phone_number).lstrip('+')})"
    return label


def line_options():
    """Options of the wizard's dropdown, WhatsApp Web connections first."""
    options = []
    for kind in (WEB, API):
        model = _account_model(kind)
        if model is None:
            continue
        for account in model._base_manager.filter(active=True).order_by("id"):
            options.append({"value": line_key(kind, account.pk), "label": line_label(kind, account)})
    return options


def default_line():
    """The line the wizard opens on, or None when the default account is gone.

    The WhatsApp Web connection of the ``DEFAULT_ACCOUNT_NAME`` number; the API
    account itself when that number has no WhatsApp Web connection.
    """
    model = _account_model(API)
    if model is None:
        return None
    account = (
        model._base_manager.filter(active=True, name__icontains=DEFAULT_ACCOUNT_NAME)
        .order_by("id")
        .first()
    )
    if account is None:
        return None
    web = None
    if _account_model(WEB) is not None:
        from modules.wa_web.services.paired_line import paired_wa_web_account

        web = paired_wa_web_account(account)
    return line_key(WEB, web.pk) if web else line_key(API, account.pk)


def customers_domain(value):
    """Domain of the Customers picker (``base.partner``) for a line: partners
    who have a one-to-one chat on it (groups are left out).

    An empty or unknown line matches NOTHING: ``in [None]`` is SQL
    ``IN (NULL)``. (An ``eq`` null fails the engine's validation and the
    selection endpoint then drops the whole domain, i.e. offers every partner.)
    """
    kind, account_id = parse_line(value) or (None, None)
    if kind is None:
        return {
            "filters": {
                "operator": "and",
                "filters": [
                    {"field": "social_conversations__social_account_object_id", "operator": "in", "value": [None]},
                ],
            }
        }
    # One filter() call, so all three conditions hold on the SAME conversation.
    return {
        "filters": {
            "operator": "and",
            "filters": [
                {"field": "social_conversations__type", "operator": "eq", "value": kind},
                {"field": "social_conversations__social_account_object_id", "operator": "eq", "value": account_id},
                {"field": "social_conversations__is_group", "operator": "eq", "value": False},
            ],
        }
    }


def line_change_result(value):
    """Shared ``@onchange`` result for the wizard's ``whatsapp_line`` field:
    narrow the Customers picker to the picked line and clear stale selections.

    Used by BOTH registrations of the onchange:
    - ``SendTicketImageAction._onchange_whatsapp_line`` (the wizard's own model
      — correct for direct API callers), and
    - ``TicketExtension._onchange_wizard_whatsapp_line`` (support.ticket — the
      model the action-slideover frontend ACTUALLY posts onchange with,
      because MiniForm's ``model`` prop carries the selected records' model).
    """
    return {"domain": {"partners": customers_domain(value)}, "value": {"partners": []}}
