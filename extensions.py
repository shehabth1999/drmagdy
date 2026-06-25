# -*- coding: utf-8 -*-
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext
from modules.base.model_inheritance import ModelExtension
from modules.base.decorators import action
from modules.base.fields import AttachmentForeignKeyField


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
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("No open lead was found for this customer."),
                'data': {},
            }

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
        from modules.support.models import Ticket

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
                    'context': {},
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

        # Ticket requires a branch (BranchMixin). It auto-fills from env.branch on
        # save, but resolve + guard here so the agent gets a friendly message.
        branch = getattr(message.env, 'branch', None)
        if branch is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("Please select a branch before creating a ticket."),
                'data': {},
            }

        partner = getattr(message.conversation, 'social_partner', None)

        # Link the ticket to its source message (enforces one-ticket-per-message).
        vals = {'branch': branch, 'source_message': message}
        if partner is not None:
            vals['partner'] = partner
            vals['email'] = partner.email or ''
            vals['phone'] = partner.phone or partner.mobile or ''

        if message.type == 'text':
            text = ''
            if isinstance(message.content, dict):
                text = (message.content.get('text') or '').strip()
            vals['description'] = text
            vals['name'] = text[:80].strip() or gettext("Out-of-stock request")
        else:  # image
            message_attachment = getattr(message, 'attachment', None)
            if message_attachment is None or not getattr(getattr(message_attachment, 'file', None), 'name', None):
                return {
                    'status': False,
                    'open_mode': 'message',
                    'message': gettext("This image has no stored file to attach."),
                    'data': {},
                }
            # Copy the chat image into a base Attachment (references the SAME file).
            vals['files'] = Attachment.from_chat_attachment(message_attachment)
            caption = (getattr(message_attachment, 'caption', '') or '').strip()
            vals['description'] = caption
            if caption:
                vals['name'] = caption[:80]
            elif partner is not None:
                vals['name'] = gettext("Request from %(n)s") % {'n': partner.name}
            else:
                vals['name'] = gettext("Out-of-stock request")

        ticket = Ticket.create(**vals)

        # Open the freshly created ticket's form in a slideover (edit mode).
        return _open_ticket(ticket, created=True)
