# -*- coding: utf-8 -*-
# Models for the drmagdy module.
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext

from modules.base.models.base import BaseModel
from modules.base.fields import AttachmentForeignKeyField
from modules.base.decorators import action


class BankRoshtat(BaseModel):
    """A bank of prescription ("roshta") images captured from chat.

    Each row is ONE prescription image. Rows are created from a single chat
    image message via the ``action_create_bank_roshtat_from_message`` server
    action (see ``drmagdy/extensions.py``). The ``message`` OneToOne enforces
    "one row per chat message" at the DB level — a message can never spawn a
    second row.
    """

    class Meta:
        verbose_name = _("Bank Roshtat")
        verbose_name_plural = _("Bank Roshtat")
        ordering = ["-created_at"]

    # Auto-generated from the source chat message when created via the server
    # action. Required — every row carries a human-readable label.
    name = models.CharField(
        max_length=255,
        verbose_name=_("Name"),
        help_text=_("Auto-generated from the chat message."),
    )

    # The chat message this row was created from. OneToOne guarantees one row
    # per message (never create two on the same message). Optional: rows may be
    # created manually without a source message.
    message = models.OneToOneField(
        "chat.message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_roshtat",
        verbose_name=_("Message"),
        help_text=_("The chat message this prescription was created from (one per message)."),
    )

    # Single prescription image. Custom attachment field (NOT a raw FK to
    # base.Attachment) — wires up upload_to, real MIME-type validation,
    # thumbnails and the attachment serializer pipeline, and serializes cleanly.
    # Files land under an organized, dedicated path.
    attachment = AttachmentForeignKeyField(
        upload_to="drmagdy/bank_roshtat/images",
        allowed_types=["image"],
        related_name="bank_roshtat_images",
        verbose_name=_("Image"),
        help_text=_("Prescription image."),
    )

    # Free-form notes, edited with the rich-text editor widget on the form.
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Notes"),
        help_text=_("Free-form notes about this prescription."),
    )

    def __str__(self):
        return self.name or f"Bank Roshtat #{self.pk}"

    @action
    def action_open_conversation(self):
        """Navigate to the chat conversation that contains this row's source
        message. Used by the "Open Conversation" button on the form/list views.

        ``self`` is the queryset of selected rows (the server-action framework
        passes it as the first arg); we act on the first one.
        """
        record = self.first()
        if record is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("No record selected."),
                'data': {},
            }

        message = record.message
        if message is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("This prescription has no linked chat message."),
                'data': {},
            }

        conversation = getattr(message, 'conversation', None)
        if conversation is None:
            return {
                'status': False,
                'open_mode': 'message',
                'message': gettext("The linked message has no conversation."),
                'data': {},
            }

        # `open_mode: 'redirect'` navigates the browser to the URL (the frontend
        # sets window.location.href). `get_chat_url()` is the canonical chat deep
        # link: /chat/?main_tab=social&sub_tab=all&chat=<conversation.id>.
        return {
            'status': True,
            'open_mode': 'redirect',
            'message': gettext("Opening conversation…"),
            'data': {'url': conversation.get_chat_url()},
        }
