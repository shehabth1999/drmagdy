# -*- coding: utf-8 -*-
"""Give ``support_ticket.delivered_at`` a time zone.

Same core ``sync_schema`` gap and same idempotent fix as
``0006_datetime_columns_with_time_zone`` (read its docstring): the column is
created as ``timestamp without time zone`` and converted here with
``AT TIME ZONE 'UTC'``. Run ``sync_schema --from-module drmagdy`` BEFORE
``migrate drmagdy`` so the column exists when this runs.
"""
from django.db import migrations


def _sql(from_type, to_type):
    return f"""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'support_ticket'
          AND column_name = 'delivered_at'
          AND data_type = '{from_type}'
    ) THEN
        ALTER TABLE support_ticket
            ALTER COLUMN delivered_at TYPE {to_type}
            USING delivered_at AT TIME ZONE 'UTC';
    END IF;
END $$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("drmagdy", "0006_datetime_columns_with_time_zone"),
    ]

    operations = [
        migrations.RunSQL(
            _sql("timestamp without time zone", "timestamp with time zone"),
            _sql("timestamp with time zone", "timestamp without time zone"),
        ),
    ]
