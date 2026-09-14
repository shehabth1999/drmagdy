# -*- coding: utf-8 -*-
# UI Views for drmagdy module.
# Real views live in their own files in this folder:
#   - lead_form_patch.py          (crm.lead form: payment_receipt)
#   - ticket_form_patch.py        (support.ticket form: pharmacy "items under order"
#                                  layout — supervisor, files, buyer, urgency, supplier
#                                  code, expected arrival, internal note, contact status,
#                                  ribbon, Send-to-WhatsApp + Cancel Order buttons)
#   - ticket_kanban_patch.py      (support.ticket kanban: category + datetime)
#   - send_ticket_image_views.py  (wizard: send ticket image to WhatsApp)
#   - cancel_ticket_views.py      (wizard: cancel order — keep / return)
#   - bank_roshtat_views.py       (drmagdy.bankroshtat list + form)
from django.utils.translation import gettext as _
