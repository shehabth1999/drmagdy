# -*- coding: utf-8 -*-
from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext
from modules.base.model_inheritance import ModelExtension
from modules.base.decorators import action, onchange
from modules.base.fields import AttachmentForeignKeyField
from modules.base.middleware import get_current_user


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


class TicketExtension(ModelExtension):
    """Add a supervisor field to support.Ticket via the drmagdy extension module."""

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

    # Single image attached to the ticket (e.g. a photo of the requested medicine
    # / prescription copied from a chat message). Custom attachment field — NOT a
    # raw ForeignKey to base.Attachment.
    files = AttachmentForeignKeyField(
        upload_to='support/tickets/files',
        allowed_types=['image'],
        related_name='ticket_files',
        verbose_name=_("Files"),
        help_text=_("Image attached to this ticket (e.g. the requested medicine / prescription)"),
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
        from modules.chat.models import Conversation, Message, MessageAttachment
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

        if not record.files or not record.files.file:
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

        # Outbound messages need a sender partner (required FK) — use the
        # current user's linked partner.
        sender_partner = getattr(user, 'partner', None)
        if sender_partner is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("Your user has no linked partner to send as."),
                'data': {},
            }

        # WhatsApp-safe absolute URL (JPEG-converts unsupported formats).
        media_url = whatsapp_media_url(record.files, media_type='image')
        if not media_url:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("Could not build a public URL for the image."),
                'data': {},
            }

        caption = (form.message or '').strip()
        account_ct = ContentType.objects.get_for_model(type(account))
        broadcaster = MessageSenderService()

        sent = 0
        skipped_names = []
        for partner in partners:
            conversation = Conversation.objects.filter(
                social_account_content_type=account_ct,
                social_account_object_id=account.id,
                social_partner=partner,
            ).first()
            if conversation is None:
                skipped_names.append(partner.name or str(partner.pk))
                continue

            # One MessageAttachment row per message (OneToOne), all pointing at
            # the same stored file — no download/copy.
            chat_attachment = MessageAttachment.from_base_attachment(
                record.files, caption=caption or None,
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
            if caption:
                content['attachment']['caption'] = caption
                content['caption'] = caption

            # pre_create auto-sets direction='outbound' + social account fields;
            # post_create fires account.handle_message → Celery WhatsApp send.
            message = Message.objects.create(
                conversation=conversation,
                sender=sender_partner,
                type='image',
                content=content,
            )

            chat_attachment.message = message
            chat_attachment.linked_to_message = True
            chat_attachment.save(update_fields=['message', 'linked_to_message'])

            # Push the new message over WebSocket so agents see it live.
            try:
                broadcaster._broadcast_message(conversation, message)
            except Exception:  # noqa: BLE001 - broadcast failure must not block sending
                pass

            sent += 1

        if sent == 0:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("No conversation on %(number)s for: %(names)s. Pick the number first — the customer list only shows customers of that number.") % {
                    'number': account.phone_number or account.name,
                    'names': ', '.join(skipped_names),
                },
                'data': {},
            }

        message_text = gettext("Image queued for %(sent)d customer(s).") % {'sent': sent}
        if skipped_names:
            message_text += " " + gettext("Skipped (no conversation on this number): %(names)s.") % {'names': ', '.join(skipped_names)}

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
        """Single text/image message -> create a support ticket and open it in a
        slideover for fast editing.

        - text message: the text becomes the ticket Description, with an
          auto-generated Subject.
        - image message: the image is copied into the ticket's `files` field
          (via Attachment.from_chat_attachment), and the caption (if any) seeds
          the Subject/Description.
        """
        from modules.base.models.attachment import Attachment
        from modules.support.models import Ticket, TicketStage

        message = self.first()
        if message is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("No message selected."),
                'data': {},
            }

        # Guard: only text or image (the button schema enforces this too, but
        # never trust the client).
        if message.type not in ('text', 'image'):
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("This action only works on a single text or image message."),
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

        # ONE TICKET PER MESSAGE. Look across ALL tickets (all_objects bypasses the
        # branch/active manager filters) so we also catch a ticket that is closed
        # or sits in another branch. If found, just re-open it — never duplicate.
        existing = Ticket.all_objects.filter(source_message=message).first()
        if existing is not None:
            return _open_ticket(existing, created=False)

        # Ticket requires a branch (BranchMixin). The form auto-fills it from
        # env.branch on save, but resolve + guard here so the agent gets a
        # friendly message and the form is pre-filled with the right branch.
        branch = getattr(message.env, 'branch', None)
        if branch is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("Please select a branch before creating a ticket."),
                'data': {},
            }

        partner = getattr(message.conversation, 'social_partner', None)

        # New tickets should land in the "New" stage (cached for 1 day per
        # company). Resolve the Stage object so the relation field pre-fills with
        # a proper label; a stale/deleted id just yields None and is skipped.
        stage_id = get_new_ticket_stage_id(message.env)
        stage = TicketStage.objects.filter(pk=stage_id).first() if stage_id else None

        # Build the create-form defaults instead of creating the ticket. The
        # server-action layer turns model instances into {id, name} for relation
        # widgets; the image is a serialized dict that round-trips to the SAME
        # attachment on save. `source_message` is hidden but still saved (it
        # enforces one-ticket-per-message once the agent saves).
        default_fields = {'branch': branch, 'source_message': message}
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

        if message.type == 'text':
            text = ''
            if isinstance(message.content, dict):
                text = (message.content.get('text') or '').strip()
            default_fields['description'] = text
            default_fields['name'] = text[:80].strip() or gettext("Out-of-stock request")
        else:  # image
            message_attachment = getattr(message, 'attachment', None)
            if message_attachment is None or not getattr(getattr(message_attachment, 'file', None), 'name', None):
                return {
                    'status': False,
                    'open_mode': 'message',
                    'message': gettext("This image has no stored file to attach."),
                    'data': {},
                }
            # Copy the chat image into a base Attachment (references the SAME file)
            # and pre-fill the `files` widget with it.
            attachment = Attachment.from_chat_attachment(message_attachment)
            default_fields['files'] = _serialize_attachment_for_form(attachment)
            caption = (getattr(message_attachment, 'caption', '') or '').strip()
            default_fields['description'] = caption
            if caption:
                default_fields['name'] = caption[:80]
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
