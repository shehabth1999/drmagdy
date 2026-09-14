# -*- coding: utf-8 -*-
import logging

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext
from modules.base.model_inheritance import ModelExtension
from modules.base.decorators import action, onchange
from modules.base.fields import AttachmentForeignKeyField, AttachmentManyToManyField
from modules.base.middleware import get_current_user

from . import ticket_stages as st
from .choices import CANCEL_MODE_CHOICES, CONTACT_STATUS_CHOICES, RIBBON_CHOICES

logger = logging.getLogger(__name__)


# Cache the resolved "New" ticket-stage id for a day. Stages are company-scoped
# (CompanyMixin) and change rarely, so a per-company cache turns a SQL hit into a
# memory hit on the hot path (every "Create Ticket" click).
NEW_TICKET_STAGE_CACHE_TIMEOUT = 60 * 60 * 24  # 1 day, in seconds


def _new_ticket_stage_cache_key(company_id):
    return f"drmagdy:support:new_ticket_stage_id:{company_id or 0}"


def get_new_ticket_stage_id(env, force_refresh=False):
    """Return the id of the stage new tickets should land in, cached for 1 day.

    Priority (resolved in a SINGLE query): a stage named "New", else the first
    OPEN stage by sequence, else any stage by sequence. Returns ``None`` if no
    stages exist (never cached, so it re-checks next time).

    Pass ``force_refresh=True`` to bypass + rewrite the cache — used to recover
    when a stale cached id points at a deleted stage and the ticket insert fails.
    """
    company = getattr(env, 'company', None)
    cache_key = _new_ticket_stage_cache_key(getattr(company, 'id', None))

    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    from modules.support.models import TicketStage

    stage_id = (
        TicketStage.objects.annotate(
            _match_rank=models.Case(
                models.When(name__iexact="New", then=models.Value(0)),
                models.When(is_closed=False, then=models.Value(1)),
                default=models.Value(2),
                output_field=models.IntegerField(),
            )
        )
        .order_by("_match_rank", "sequence")
        .values_list("id", flat=True)
        .first()
    )

    if stage_id is not None:
        cache.set(cache_key, stage_id, NEW_TICKET_STAGE_CACHE_TIMEOUT)
    return stage_id


def _serialize_attachment_for_form(attachment):
    """Serialize a base Attachment into the dict shape the image/files widgets
    render in a create form.

    The dict carries a ``url`` (so the widget shows the image) and an ``id`` — on
    save the attachment pipeline (``Attachment.process_attachment_data``) resolves
    a dict-with-id back to the SAME attachment, so no duplicate is created and the
    original chat file is reused. Returns ``None`` for a missing attachment.
    """
    if attachment is None:
        return None
    try:
        url = attachment.file.url if getattr(attachment, 'file', None) else None
    except Exception:
        url = None
    return {
        'id': attachment.id,
        'name': attachment.name,
        'url': url,
        'thumbnail_url': url,
        'mime_type': attachment.mime_type,
        'size': attachment.size,
        'type': attachment.type,
    }


def _aware(value):
    """Return ``value`` as a timezone-aware datetime.

    A form save delivers ``expected_arrival_at`` as the browser sent it, i.e. a
    naive datetime in the site's timezone; ``timezone.now()`` is aware, and
    Python refuses to ORDER a naive and an aware datetime ("can't compare
    offset-naive and offset-aware datetimes"). Django would make the value
    aware on its way to the database anyway, so do the same here before any
    comparison. Non-datetimes (None, dates) pass through untouched.
    """
    if value is None or not hasattr(value, 'tzinfo'):
        return value
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _whatsapp_window_closed(conversation):
    """True when WhatsApp would refuse a free-form message in this conversation.

    WhatsApp only accepts non-template messages (images included) within 24 hours
    of the customer's last INBOUND message (error 131047 "re-engagement message").
    Reuses the core check from modules.chat.tasks; falls back to the same query.
    """
    try:
        from modules.chat.tasks import _whatsapp_window_closed as core_check

        return core_check(conversation)
    except Exception:  # pragma: no cover - core helper moved
        from datetime import timedelta

        from modules.chat.models import Message

        last_in = (
            Message.objects.filter(conversation=conversation, direction='inbound')
            .order_by('-created_at').values_list('created_at', flat=True).first()
        )
        return not last_in or (timezone.now() - last_in) > timedelta(hours=24)


def compute_ribbon_state(ticket, now=None, company_id=None):
    """Value of ``Ticket.ribbon_state`` for the form ribbon.

    Precedence (first match wins): cancelled > overdue > returned >
    very_important > urgent > nothing. "Overdue" means the expected arrival
    time has passed while the ticket is still in "اصناف تحت الطلب". Called from
    ``TicketExtension.pre_save`` on every save and from the arrival reminder
    task (which flips a ticket to overdue at its due time).
    """
    now = now or timezone.now()
    if getattr(ticket, 'is_cancelled', False):
        return 'cancelled'
    arrival = _aware(getattr(ticket, 'expected_arrival_at', None))
    if arrival and arrival <= now and st.role_of(ticket.stage_id, company_id) == st.UNDER_ORDER:
        return 'overdue'
    if getattr(ticket, 'is_returned', False):
        return 'returned'
    if getattr(ticket, 'is_very_important', False):
        return 'very_important'
    if getattr(ticket, 'is_urgent', False):
        return 'urgent'
    return None


def _cancel_note(mode, reason, old_stage_name, user):
    """HTML chatter note recording what the cancel wizard did."""
    who = getattr(user, 'name', None) or getattr(user, 'email', None) or '-'
    if mode == 'cancel_keep':
        head = gettext("Order cancelled — item kept; ticket closed.")
    else:
        head = gettext("Order returned to the shelf — ticket restarted as new and marked returned.")
    parts = [
        head,
        gettext("Previous stage: %(stage)s") % {'stage': old_stage_name},
        gettext("By: %(user)s") % {'user': who},
    ]
    if reason:
        parts.append(gettext("Reason: %(reason)s") % {'reason': reason})
    return "<br/>".join(parts)


class TicketExtension(ModelExtension):
    """drmagdy additions to support.Ticket: supervisor, images, chat source
    message, and the pharmacy "items under order" workflow (buyer, urgency,
    supplier code, expected arrival + reminder, contact status,
    cancel / return, ribbon)."""

    _inherit = 'support.ticket'
    _depends = ['support', 'chat']

    supervisor = models.ForeignKey(
        'base.user',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supervised_tickets',
        verbose_name=_("Supervisor"),
        help_text=_("Supervisor responsible for this ticket"),
    )

    # Images attached to the ticket (e.g. photos of the requested medicine /
    # prescription copied from chat messages). Custom attachment M2M — NOT a
    # raw M2M to base.Attachment. Was an AttachmentForeignKeyField (single)
    # until 2026-07-23; existing files_id values were migrated into the M2M
    # join table when the schema change was applied.
    files = AttachmentManyToManyField(
        upload_to='support/tickets/files',
        allowed_types=['image'],
        related_name='ticket_files',
        blank=True,
        verbose_name=_("Files"),
        help_text=_("Images attached to this ticket (e.g. the requested medicine / prescription)"),
    )

    # The chat message this ticket was created from. OneToOne enforces "one
    # ticket per message" at the DB level — a message can never spawn a second
    # ticket, even after the first is closed. Reverse: message.generated_ticket.
    source_message = models.OneToOneField(
        'chat.message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_ticket',
        verbose_name=_("Source Message"),
        help_text=_("The chat message this ticket was created from (one ticket per message)."),
    )

    # ------------------------------------------------------------------
    # Items-under-order workflow (2026-09-14). All columns nullable or
    # defaulted so sync_schema adds them to the populated table in place.
    # ------------------------------------------------------------------
    buyer = models.ForeignKey(
        'base.user',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='drmagdy_bought_tickets',
        verbose_name=_("Buyer"),
        help_text=_("User who buys the ordered item"),
    )
    is_urgent = models.BooleanField(
        default=False,
        verbose_name=_("Urgent"),
        help_text=_("Off = normal (عادي), on = urgent (مستعجل)"),
    )
    is_very_important = models.BooleanField(
        default=False,
        verbose_name=_("Very important — obtain from anywhere"),
        help_text=_("The order must be obtained from any source because of its importance"),
    )
    supplier_code = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name=_("Supplier code"),
    )
    expected_arrival_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Expected arrival"),
        help_text=_("When the ordered item should arrive"),
    )
    contact_status = models.CharField(
        max_length=32,
        choices=CONTACT_STATUS_CHOICES,
        null=True,
        blank=True,
        verbose_name=_("Contact status"),
        help_text=_("Result of contacting the customer once the item arrived"),
    )
    is_cancelled = models.BooleanField(default=False, verbose_name=_("Cancelled"))
    is_returned = models.BooleanField(default=False, verbose_name=_("Returned"))
    cancel_mode = models.CharField(
        max_length=16,
        choices=CANCEL_MODE_CHOICES,
        null=True,
        blank=True,
        verbose_name=_("Cancel outcome"),
    )
    cancel_reason = models.TextField(null=True, blank=True, verbose_name=_("Cancel reason"))
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Cancelled / returned on"))
    return_count = models.IntegerField(default=0, verbose_name=_("Times returned"))
    ribbon_state = models.CharField(
        max_length=20,
        choices=RIBBON_CHOICES,
        null=True,
        blank=True,
        verbose_name=_("Ribbon"),
    )
    # Stamped by drmagdy.tasks.notify_due_ticket_arrivals after the one-time
    # alert; cleared in pre_save when the date changes or the ticket re-enters
    # "اصناف تحت الطلب" (re-arm).
    arrival_notified_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Arrival alert sent on"))

    def _is_blank(self, field_name):
        attname = f"{field_name}_id"
        value = getattr(self, attname) if hasattr(self, attname) else getattr(self, field_name, None)
        return value is None or (isinstance(value, str) and not value.strip())

    def _rearm_arrival_reminder(self):
        self.arrival_notified_at = None

    def pre_save(self):
        """Stage-transition rules, closed_at bookkeeping, reminder re-arming and
        ribbon state.

        Chained by the extension system AFTER the model's own hooks — never call
        super() here. Runs for form saves, the status pill and kanban drags
        (all go through ``Ticket.save()``); ``@onchange`` does not, which is why
        the "required in stage X" rules live here and not in the view schema
        (frontend ``required`` is boolean-only anyway).
        """
        now = timezone.now()
        # Normalise a naive datetime coming from the form so every comparison
        # below (and the DB write) sees an aware value.
        if self.expected_arrival_at is not None:
            self.expected_arrival_at = _aware(self.expected_arrival_at)
        old = None
        if self.pk:
            old = type(self)._base_manager.filter(pk=self.pk).values('stage_id', 'expected_arrival_at').first()
        old_stage_id = old['stage_id'] if old else None
        company_id = getattr(getattr(self, 'branch', None), 'company_id', None)
        stage_changed = self.stage_id != old_stage_id

        if (
            st.ENFORCE_STAGE_RULES
            and stage_changed
            and self.stage_id
            and not getattr(self, '_skip_stage_rules', False)
        ):
            new_role = st.role_of(self.stage_id, company_id)
            rule = st.TRANSITION_RULES.get(new_role) or {}
            required = dict(rule.get('required', {}))
            required.update(rule.get('required_from', {}).get(st.role_of(old_stage_id, company_id), {}))
            missing = [str(label) for name, label in required.items() if self._is_blank(name)]
            if missing:
                raise ValidationError(
                    gettext('Cannot move the ticket to "%(stage)s" before filling: %(fields)s') % {
                        'stage': self.stage.name,
                        'fields': '، '.join(missing),
                    }
                )

        if stage_changed:
            new_role = st.role_of(self.stage_id, company_id)
            old_role = st.role_of(old_stage_id, company_id)
            if new_role in st.CLOSED:
                if not self.closed_at:
                    self.closed_at = now
            elif old_role in st.CLOSED:
                self.closed_at = None
            if new_role == st.UNDER_ORDER:
                self._rearm_arrival_reminder()

        if old is None or old['expected_arrival_at'] != self.expected_arrival_at:
            self._rearm_arrival_reminder()

        self.ribbon_state = compute_ribbon_state(self, now, company_id)

    @action
    def action_cancel_ticket(queryset, form):
        """Cancel wizard handler (``drmagdy_cancel_ticket_form_view``).

        ``form.mode``:
          * ``cancel_keep``   → keep the item: ticket closes into "تمت المعالجة"
                                 and is flagged cancelled.
          * ``cancel_return`` → item back on the shelf: the SAME ticket restarts
                                 in "جديد", flagged returned; every other field
                                 is kept (customer decision, 2026-09-14).
        Both post an internal chatter note. Stage rules are bypassed for these
        programmatic moves.
        """
        user = get_current_user()
        mode = getattr(form, 'mode', None)
        if mode not in dict(CANCEL_MODE_CHOICES):
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("Please choose what happens to the item."),
                'data': {},
            }
        reason = (getattr(form, 'reason', '') or '').strip()
        now = timezone.now()
        done, skipped = 0, []

        for ticket in queryset:
            if ticket.is_cancelled:
                skipped.append(f"#{ticket.id}")
                continue

            company_id = getattr(getattr(ticket, 'branch', None), 'company_id', None)
            target_role = st.PROCESSED if mode == 'cancel_keep' else st.NEW
            target_stage_id = st.stage_id(target_role, company_id)
            if not target_stage_id:
                return {
                    'status': False,
                    'open_mode': 'message',
                    'message': gettext('Ticket stage "%(stage)s" was not found; nothing was changed.') % {
                        'stage': st.STAGE_NAMES[target_role],
                    },
                    'data': {},
                }

            old_stage_name = ticket.stage.name if ticket.stage_id else '-'
            ticket._skip_stage_rules = True
            ticket.cancel_mode = mode
            ticket.cancel_reason = reason or None
            ticket.cancelled_at = now
            if mode == 'cancel_keep':
                ticket.is_cancelled = True
                ticket.stage_id = target_stage_id
                ticket.closed_at = now
            else:
                ticket.is_returned = True
                ticket.return_count = (ticket.return_count or 0) + 1
                ticket.stage_id = target_stage_id
                ticket.closed_at = None
            ticket.save()  # full save → pre_save recomputes ribbon / bookkeeping

            try:
                ticket.message_post(body=_cancel_note(mode, reason, old_stage_name, user), message_type='note')
            except Exception:  # noqa: BLE001 - chatter is best effort
                logger.exception("drmagdy: cancel note failed for ticket #%s", ticket.pk)
            done += 1

        message = gettext("%(n)d ticket(s) processed.") % {'n': done}
        if skipped:
            message += " " + gettext("Already cancelled: %(ids)s") % {'ids': ', '.join(skipped)}
        return {
            'status': True,
            'open_mode': 'message',
            'message': message,
            'data': {},
            'on_success': {'type': 'refresh'},
        }

    @onchange('whatsapp_account')
    def _onchange_wizard_whatsapp_account(self):
        """Mirror of the Send-Ticket-Image wizard's number onchange, registered
        on support.ticket.

        Why here: the wizard opens as a menu-type action slideover, and the
        frontend (MiniForm) posts onchange with the SELECTED records' model
        (``support.ticket``) — its ``model`` prop takes priority over the
        wizard view's model — so the registration on
        ``drmagdy.sendticketimageaction`` is never hit from the UI. Tickets
        have no ``whatsapp_account`` field, so this can ONLY fire from that
        wizard form. The account id is read from the posted values via the
        onchange proxy's ``_original_data`` (a Ticket instance can't hold it).

        Effect in the wizard: clears the Customers (العملاء) field and narrows
        its picker to customers of the selected number.
        """
        from .models import send_wizard_account_change_result

        raw = getattr(self, '_original_data', {}).get('whatsapp_account')
        account_id = raw.get('id') if isinstance(raw, dict) else raw
        return send_wizard_account_change_result(account_id)

    @action
    def action_send_ticket_image_to_conversations(queryset, form):
        """Send this ticket's image (``files``, with an optional caption) to the
        WhatsApp conversations of the customers picked in the wizard.

        Opened via the `type: "menu"` button on the ticket form view; `form` is
        the saved ``drmagdy.SendTicketImageAction`` transient holding the wizard
        input. For each selected customer we resolve their ONE conversation on
        the selected WhatsApp number (unique per the chat
        `unique_social_partner_account_combination` constraint), create a chat
        MessageAttachment that references the SAME stored file (no copy), and
        create the outbound Message — `Message.post_create` then queues the
        actual WhatsApp send (`process_handling_message`) which reads
        `content.attachment.url` + `content.caption`.
        """
        from django.contrib.contenttypes.models import ContentType
        from modules.base.models import Partner
        from modules.chat.models import Conversation, ConversationMember, Message, MessageAttachment
        from modules.chat.services.message_sender_service import MessageSenderService
        from modules.whatsapp.utils.media import whatsapp_media_url

        # Managers/admins only (admins imply support.managers). The button is
        # also hidden via allowed_groups, but the UI is not a security layer —
        # enforce here so a direct API call can't bypass it.
        user = get_current_user()
        if user is None or (
            not user.is_superuser and not user.has_groups(['support.managers'])
        ):
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("Only support managers can send ticket images to WhatsApp."),
                'data': {},
            }

        record = queryset.first()
        if record is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("No record selected."),
                'data': {},
            }

        # `files` is now an M2M — gather every attached image that has a file.
        images = [a for a in record.files.all() if getattr(a, 'file', None)]
        if not images:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("This ticket has no image to send."),
                'data': {},
            }

        account = form.whatsapp_account
        partners = list(form.partners.all())
        if not account or not partners:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("Select a WhatsApp number and at least one customer."),
                'data': {},
            }

        # Outbound messages need a sender partner (required FK). Preferred
        # sender: the user who runs the action. Per-conversation fallback: if
        # that partner is not an active participant of the conversation, send
        # as the Genie system partner instead (same partner the AI replies
        # use) — see the loop below.
        user_partner = getattr(user, 'partner', None)
        genie_partner = Partner.all_objects.filter(
            ai_agent=True, email="genie@genie-erp.com",
        ).first()
        if user_partner is None and genie_partner is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("No sender available: your user has no linked partner and the Genie system partner is missing."),
                'data': {},
            }

        # Resolve each image to a WhatsApp-safe absolute URL once (JPEG-converts
        # unsupported formats). Skip any that fail to produce a URL.
        image_urls = []
        for att in images:
            url = whatsapp_media_url(att, media_type='image')
            if url:
                image_urls.append((att, url))
        if not image_urls:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("Could not build a public URL for the ticket image(s)."),
                'data': {},
            }

        caption = (form.message or '').strip()
        account_ct = ContentType.objects.get_for_model(type(account))
        broadcaster = MessageSenderService()

        # Pre-flight: resolve EVERY selected customer's conversation on the
        # chosen number BEFORE sending anything. A customer with no
        # conversation on this number means the picker handed us something it
        # should never have offered (its domain is meant to narrow the list to
        # that number's customers). Refuse the whole send rather than deliver
        # to the subset that happens to match — a partial send is invisible to
        # the user and reads as "only the first customer got the message".
        conversation_by_partner = {}
        missing_names = []
        for partner in partners:
            conversation = Conversation.objects.filter(
                social_account_content_type=account_ct,
                social_account_object_id=account.id,
                social_partner=partner,
            ).first()
            if conversation is None:
                missing_names.append(partner.name or str(partner.pk))
            else:
                conversation_by_partner[partner.pk] = conversation

        if missing_names:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext(
                    "Nothing was sent. These customers have no conversation on %(number)s: %(names)s. "
                    "Pick the number first — the customer list only shows customers of that number."
                ) % {
                    'number': account.phone_number or account.name,
                    'names': ', '.join(missing_names),
                },
                'data': {},
            }

        # WhatsApp refuses free-form messages (images included) to a customer who
        # has not written to this number in the last 24 hours (error 131047).
        # The refusal arrives asynchronously, so without this check the wizard
        # reported "queued" while the customer silently never received the
        # image. Skip those customers and name them in the result.
        closed_names, open_partners = [], []
        for partner in partners:
            if _whatsapp_window_closed(conversation_by_partner[partner.pk]):
                closed_names.append(partner.name or str(partner.pk))
            else:
                open_partners.append(partner)
        if not open_partners:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext(
                    "Nothing was sent: WhatsApp only accepts messages to customers who wrote to this "
                    "number within the last 24 hours. Outside the window: %(names)s"
                ) % {'names': ', '.join(closed_names)},
                'data': {},
            }

        sent = 0
        for partner in open_partners:
            conversation = conversation_by_partner[partner.pk]

            # Sender for THIS conversation: the action user if they are an
            # active participant (soft-removed 'removed' rows don't count),
            # otherwise the Genie system partner.
            sender_partner = None
            if user_partner is not None and ConversationMember.objects.filter(
                conversation=conversation, user=user_partner,
            ).exclude(role='removed').exists():
                sender_partner = user_partner
            else:
                sender_partner = genie_partner or user_partner

            # One outbound image message per attached image. The caption rides
            # on the FIRST image only (WhatsApp album convention) so the text
            # isn't repeated under every photo.
            for idx, (att, media_url) in enumerate(image_urls):
                msg_caption = caption if idx == 0 else ''

                # One MessageAttachment row per message (OneToOne), all pointing
                # at the same stored file — no download/copy.
                chat_attachment = MessageAttachment.from_base_attachment(
                    att, caption=msg_caption or None,
                )

                content = {
                    'attachment': {
                        'id': str(chat_attachment.id),
                        'filename': chat_attachment.file_name,
                        'file_size': chat_attachment.file_size,
                        'file_type': chat_attachment.file_type,
                        'mime_type': chat_attachment.mime_type,
                        'url': media_url,
                        'download_status': chat_attachment.download_status,
                    },
                }
                if msg_caption:
                    content['attachment']['caption'] = msg_caption
                    content['caption'] = msg_caption

                # pre_create auto-sets direction='outbound' + social account
                # fields; post_create fires account.handle_message → Celery send.
                message = Message.objects.create(
                    conversation=conversation,
                    sender=sender_partner,
                    type='image',
                    content=content,
                )

                chat_attachment.message = message
                chat_attachment.linked_to_message = True
                chat_attachment.save(update_fields=['message', 'linked_to_message'])

                # Push each new message over WebSocket so agents see it live.
                try:
                    broadcaster._broadcast_message(conversation, message)
                except Exception:  # noqa: BLE001 - broadcast must not block sending
                    pass

            sent += 1

        message_text = gettext("%(imgs)d image(s) queued for %(sent)d customer(s).") % {'imgs': len(image_urls), 'sent': sent}
        if closed_names:
            message_text += " " + gettext(
                "Skipped %(n)d customer(s) outside the 24-hour WhatsApp window "
                "(no message from them in the last 24h): %(names)s"
            ) % {'n': len(closed_names), 'names': ', '.join(closed_names)}

        return {
            'status': True,
            'open_mode': 'message',
            'message': message_text,
            'data': {},
        }


class LeadExtension(ModelExtension):
    """Store the payment-receipt image used to close a lead as Won."""

    _inherit = 'crm.lead'
    _depends = ['crm', 'chat']

    # Use the project's custom attachment field (NOT a raw ForeignKey to
    # base.Attachment) — it wires up upload_to, MIME-type validation, thumbnails
    # and the attachment serializer pipeline, and serializes cleanly for the
    # migration-free extension system.
    payment_receipt = AttachmentForeignKeyField(
        upload_to='crm/leads/payment_receipts',
        allowed_types=['image'],
        related_name='lead_payment_receipts',
        verbose_name=_("Payment Receipt"),
        help_text=_("Payment receipt image used to mark this lead as Won"),
    )

    # The chat message whose receipt closed this lead. OneToOne links the message
    # to the lead (one lead per message), mirroring Ticket.source_message.
    # Reverse: message.won_lead.
    source_message = models.OneToOneField(
        'chat.message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='won_lead',
        verbose_name=_("Source Message"),
        help_text=_("The chat message whose payment receipt marked this lead as Won."),
    )


class MessageExtension(ModelExtension):
    """Chat message server-action: turn a customer's payment-receipt image into a
    Won lead.

    The agent selects ONE inbound image message (a payment receipt), clicks the
    action, and we:
      1. copy the chat image into a base Attachment (same underlying file — no
         re-upload — via Attachment.from_chat_attachment),
      2. link it to the customer's open lead as `payment_receipt`,
      3. mark that lead as Won.
    """

    _inherit = 'chat.message'
    _depends = ['base', 'chat', 'crm']

    @action
    def action_lead_won_from_receipt(self):
        """Single image message -> copy to base Attachment, attach to the
        customer's open lead, mark the lead as Won."""
        from modules.base.models.attachment import Attachment

        message = self.first()
        if message is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("No message selected."),
                'data': {},
            }

        # Guard: single image message only (the button schema enforces this too,
        # but never trust the client).
        if message.type != 'image':
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("This action only works on a single image message."),
                'data': {},
            }

        # `MessageAttachment` is a OneToOne on Message (related_name='attachment').
        message_attachment = getattr(message, 'attachment', None)
        if message_attachment is None or not getattr(getattr(message_attachment, 'file', None), 'name', None):
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("This image has no stored file to copy."),
                'data': {},
            }

        # Resolve the customer's open lead from the conversation's social partner.
        conversation = message.conversation
        partner = getattr(conversation, 'social_partner', None)
        if partner is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("No customer is linked to this conversation."),
                'data': {},
            }

        # `last_lead` (crm.PartnerExtension) = the partner's most recent OPEN lead.
        lead = getattr(partner, 'last_lead', None)
        if lead is None:
            # No open lead for this customer — auto-generate one so the receipt
            # always has a lead to close (this action creates directly, on
            # purpose). Branch is required (Lead is BranchMixin): resolve from
            # context, falling back to the first branch like the WhatsApp
            # lead-capture task does.
            from modules.crm.models import Lead

            branch = getattr(message.env, 'branch', None)
            if branch is None:
                from modules.base.models import Branch
                branch = Branch.objects.first()

            lead_vals = {
                'name': (getattr(partner, 'name', '') or gettext("Lead from receipt")),
                'partner': partner,
                'email': partner.email or '',
                'phone': partner.phone or getattr(partner, 'mobile', '') or '',
                'branch': branch,
            }

            # Assign the auto-created lead to the agent who ran the action (the
            # onchange that would set partner.sales_agent does NOT fire on a
            # backend create, so assigned_to would otherwise be null).
            # `get_current_user()` reads the thread-local request context (what
            # env.user resolves to) — record-independent and works regardless of
            # the queryset class. Returns the authenticated user or None.
            current_user = get_current_user()
            if current_user:
                lead_vals['assigned_to'] = current_user

            lead = Lead.create(**lead_vals)

        # Copy the chat image into a base Attachment (references the SAME file).
        attachment = Attachment.from_chat_attachment(message_attachment)

        # Link the receipt + the source chat message, persist, then move the
        # lead to the Won stage.
        lead.payment_receipt = attachment
        lead.source_message = message
        lead.save()
        lead.mark_as_won()

        # Open the lead's form directly in a slideover (edit mode) so the agent
        # sees the saved receipt + Won stage and can keep editing.
        return {
            'status': True,
            'open_mode': 'slideover',
            'message': gettext('Receipt saved and lead "%(name)s" marked as Won.') % {'name': lead.name},
            'data': {
                'menu_item_key': 'crm_main_menu_my_sales',
                'view_type': 'form',
                'id': lead.id,
                'context': {},
                'type': 'action',
                'title': gettext("Lead: %(name)s") % {'name': lead.name},
            },
        }

    @action
    def action_create_ticket_from_message(self):
        """One or more text/image messages -> create ONE support ticket and open
        it in a slideover for fast editing.

        `files` is an M2M, so selecting several image messages attaches ALL their
        images to a single ticket. Behaviour:
        - text message(s): their text is combined into the ticket Description.
        - image message(s): each image is copied into a base Attachment (via
          Attachment.from_chat_attachment) and added to the ticket's `files`;
          any captions are folded into the Description.
        - Subject seeds from the first text/caption, else the partner name.
        """
        from modules.base.models.attachment import Attachment
        from modules.support.models import Ticket, TicketStage

        messages = list(self)
        if not messages:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("No message selected."),
                'data': {},
            }

        # Guard: only text or image (the button schema enforces this too, but
        # never trust the client).
        if any(m.type not in ('text', 'image') for m in messages):
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("This action only works on text or image messages."),
                'data': {},
            }

        def _open_ticket(ticket, created):
            """Directly open the ticket's form in a slideover (edit mode).

            ``created`` only changes the toast wording — it does NOT chain any
            follow-up action; the form just opens.
            """
            return {
                'status': True,
                'open_mode': 'slideover',
                'message': gettext("Ticket created.") if created else gettext("Ticket opened."),
                'data': {
                    'menu_item_key': 'support_main_menu_tickets_my_tickets',
                    'view_type': 'form',
                    'id': ticket.id,
                    # Pass the assignee through as context (default_fields) for the
                    # opened form (works from both the message list and form views).
                    'context': {'default_fields': {'assigned_to': ticket.assigned_to_id}} if ticket.assigned_to_id else {},
                    'type': 'action',
                    'title': gettext("Ticket: %(name)s") % {'name': ticket.name},
                },
            }

        # ONE TICKET PER MESSAGE. If ANY selected message already has a ticket
        # (all_objects bypasses branch/active filters so we also catch closed /
        # other-branch tickets), just re-open it — never duplicate.
        existing = Ticket.all_objects.filter(source_message__in=messages).first()
        if existing is not None:
            return _open_ticket(existing, created=False)

        # All selected messages share one conversation, so derive branch /
        # partner / stage context from the first message.
        first = messages[0]

        # Ticket requires a branch (BranchMixin). The form auto-fills it from
        # env.branch on save, but resolve + guard here so the agent gets a
        # friendly message and the form is pre-filled with the right branch.
        branch = getattr(first.env, 'branch', None)
        if branch is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("Please select a branch before creating a ticket."),
                'data': {},
            }

        partner = getattr(first.conversation, 'social_partner', None)

        # New tickets should land in the "New" stage (cached for 1 day per
        # company). Resolve the Stage object so the relation field pre-fills with
        # a proper label; a stale/deleted id just yields None and is skipped.
        stage_id = get_new_ticket_stage_id(first.env)
        stage = TicketStage.objects.filter(pk=stage_id).first() if stage_id else None

        # Build the create-form defaults instead of creating the ticket. The
        # server-action layer turns model instances into {id, name} for relation
        # widgets; images are serialized dicts that round-trip to the SAME
        # attachments on save. `source_message` (the FIRST message) is hidden but
        # still saved (it enforces one-ticket-per-message once the agent saves).
        default_fields = {'branch': branch, 'source_message': first}
        if stage is not None:
            default_fields['stage'] = stage
        if partner is not None:
            default_fields['partner'] = partner
            default_fields['email'] = partner.email or ''
            default_fields['phone'] = partner.phone or partner.mobile or ''

        # Pre-assign to the agent who triggered the action, so the saved ticket
        # lands on their plate instead of unassigned. `get_current_user()` reads
        # the thread-local request context (what env.user resolves to) —
        # record-independent and works regardless of the queryset class.
        current_user = get_current_user()
        if current_user:
            default_fields['assigned_to'] = current_user

        # Walk every selected message (in selection order): collect image
        # attachments into the `files` M2M and text/captions into the Description.
        files = []
        text_parts = []
        for m in messages:
            if m.type == 'text':
                text = ''
                if isinstance(m.content, dict):
                    text = (m.content.get('text') or '').strip()
                if text:
                    text_parts.append(text)
            else:  # image
                message_attachment = getattr(m, 'attachment', None)
                if message_attachment is None or not getattr(getattr(message_attachment, 'file', None), 'name', None):
                    # Skip an image with no stored file rather than failing the
                    # whole batch.
                    continue
                attachment = Attachment.from_chat_attachment(message_attachment)
                files.append(_serialize_attachment_for_form(attachment))
                caption = (getattr(message_attachment, 'caption', '') or '').strip()
                if caption:
                    text_parts.append(caption)

        if not files and not text_parts:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("The selected messages have no text or image to use."),
                'data': {},
            }

        if files:
            default_fields['files'] = files

        # Description = combined text/captions; Subject = first text part, else
        # partner name, else a sensible default.
        default_fields['description'] = '\n\n'.join(text_parts).strip()
        if text_parts:
            default_fields['name'] = text_parts[0][:80]
        elif partner is not None:
            default_fields['name'] = gettext("Request from %(n)s") % {'n': partner.name}
        else:
            default_fields['name'] = gettext("Out-of-stock request")

        # Open a BLANK create form (no id) pre-filled with the defaults. The agent
        # reviews/edits and must SAVE to actually create the ticket — no
        # auto-create.
        return {
            'status': True,
            'open_mode': 'slideover',
            'message': gettext("Review the details and save to create the ticket."),
            'data': {
                'menu_item_key': 'support_main_menu_tickets_my_tickets',
                'view_type': 'form',
                # No 'id' -> the form opens in create mode.
                'context': {'default_fields': default_fields},
                'type': 'action',
                'title': gettext("New Ticket"),
            },
        }

    @action
    def action_create_bank_roshtat_from_message(self):
        """Single IMAGE message -> create a BankRoshtat row (copy the chat image
        into a base Attachment) and open the new row's form in a slideover.

        Enforces one-row-per-message: if a row already exists for this message
        we re-open it instead of creating a second one.
        """
        from modules.base.models.attachment import Attachment
        from drmagdy.models import BankRoshtat

        message = self.first()
        if message is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("No message selected."),
                'data': {},
            }

        # Guard: images only (the button schema enforces this too, but never
        # trust the client).
        if message.type != 'image':
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("This action only works on a single image message."),
                'data': {},
            }

        def _open_roshtat(roshtat, created):
            """Directly open the row's form in a slideover (edit mode)."""
            return {
                'status': True,
                'open_mode': 'slideover',
                'message': gettext("Prescription saved.") if created else gettext("Prescription opened."),
                'data': {
                    'menu_item_key': 'drmagdy_main_menu_bank_roshtat',
                    'view_type': 'form',
                    'id': roshtat.id,
                    'context': {},
                    'type': 'action',
                    'title': gettext("Bank Roshtat: %(name)s") % {'name': roshtat.name},
                },
            }

        # ONE ROW PER MESSAGE. The `message` OneToOne guarantees uniqueness at
        # the DB level; here we look it up first so we re-open rather than error.
        existing = BankRoshtat.objects.filter(message=message).first()
        if existing is not None:
            return _open_roshtat(existing, created=False)

        # The image must have a stored file to copy.
        message_attachment = getattr(message, 'attachment', None)
        if message_attachment is None or not getattr(getattr(message_attachment, 'file', None), 'name', None):
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("This image has no stored file to copy."),
                'data': {},
            }

        # Copy the chat image into a base Attachment (references the SAME file —
        # no re-upload) so the `attachment` widget pre-fills with it.
        attachment = Attachment.from_chat_attachment(message_attachment)

        # Auto-generate the name from the chat: prefer the image caption, else
        # the customer's name, else a sensible default.
        partner = getattr(message.conversation, 'social_partner', None)
        caption = (getattr(message_attachment, 'caption', '') or '').strip()
        if caption:
            name = caption[:255]
        elif partner is not None and getattr(partner, 'name', None):
            name = gettext("Roshta from %(n)s") % {'n': partner.name}
        else:
            name = gettext("Roshta")

        # Build the create-form defaults instead of creating the row. `message`
        # is hidden but still saved (it enforces one-row-per-message once the
        # agent saves); the image is a serialized dict that round-trips to the
        # SAME attachment on save.
        default_fields = {
            'name': name,
            'message': message,
            'attachment': _serialize_attachment_for_form(attachment),
            'notes': caption,
        }

        # Open a BLANK create form (no id) pre-filled with the defaults. The agent
        # reviews/edits and must SAVE to actually store the prescription — no
        # auto-create.
        return {
            'status': True,
            'open_mode': 'slideover',
            'message': gettext("Review the details and save to store the prescription."),
            'data': {
                'menu_item_key': 'drmagdy_main_menu_bank_roshtat',
                'view_type': 'form',
                # No 'id' -> the form opens in create mode.
                'context': {'default_fields': default_fields},
                'type': 'action',
                'title': gettext("New Prescription"),
            },
        }
