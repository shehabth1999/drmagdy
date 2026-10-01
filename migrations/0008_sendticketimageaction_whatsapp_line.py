# -*- coding: utf-8 -*-
"""The "Send Ticket Image" wizard picks a LINE (WhatsApp API account or
WhatsApp Web connection) instead of an API account.

Both steps keep the previous release working against this schema: the new
column has a database default and the old one only becomes nullable.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('drmagdy', '0007_delivered_at_with_time_zone'),
        ('whatsapp', '0016_whatsappaccount_conversation_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='sendticketimageaction',
            name='whatsapp_line',
            field=models.CharField(blank=True, db_default='', default='', help_text='The number to send from: a WhatsApp Web connection or a WhatsApp API account.', max_length=32, verbose_name='WhatsApp Number'),
        ),
        migrations.AlterField(
            model_name='sendticketimageaction',
            name='whatsapp_account',
            field=models.ForeignKey(blank=True, help_text='The WhatsApp account (number) to send from.', null=True, on_delete=django.db.models.deletion.CASCADE, to='whatsapp.whatsappaccount', verbose_name='WhatsApp Number'),
        ),
    ]
