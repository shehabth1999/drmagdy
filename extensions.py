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
    _depends = ['support']

    supervisor = models.ForeignKey(
        'base.user',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supervised_tickets',
        verbose_name=_("Supervisor"),
        help_text=_("Supervisor responsible for this ticket"),
    )


class LeadExtension(ModelExtension):
    """Store the payment-receipt image used to close a lead as Won."""

    _inherit = 'crm.lead'
    _depends = ['crm']

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

        # Link the receipt, persist it, then move the lead to the Won stage.
        lead.payment_receipt = attachment
        lead.save()
        lead.mark_as_won()

        return {
            'status': True,
            'open_mode': 'message',
            'message': gettext('Receipt saved and lead "%(name)s" marked as Won.') % {'name': lead.name},
            'data': {},
            'on_success': {'type': 'refresh'},
        }
