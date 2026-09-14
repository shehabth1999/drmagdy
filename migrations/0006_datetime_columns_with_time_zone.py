# -*- coding: utf-8 -*-
"""Give the extension's DateTimeField columns a time zone.

``sync_schema`` (modules/base/migration_free.py) creates every extension
``DateTimeField`` as plain ``TIMESTAMP`` = ``timestamp without time zone``,
whereas Django's own migrations use ``timestamp with time zone``. With
``USE_TZ=True`` a naive column comes back from PostgreSQL as a naive datetime,
which then cannot be ordered against ``timezone.now()`` ("can't compare
offset-naive and offset-aware datetimes") and cannot be passed to
``timezone.localtime``.

Django talks to PostgreSQL with the session time zone set to UTC, so the
wall-clock values already stored in these columns are UTC: ``AT TIME ZONE
'UTC'`` converts them without shifting the instant. Idempotent: a column that
is already ``timestamp with time zone`` (or does not exist yet on a fresh
environment where sync_schema has not run) is skipped. The schema inspector
treats both timestamp flavours as one family, so sync_schema will not undo this.

Fresh environments: run ``sync_schema --from-module drmagdy`` first, then
``migrate drmagdy`` (or re-run ``migrate drmagdy 0005`` + ``0006`` afterwards).
"""
from django.db import migrations

COLUMNS = ("expected_arrival_at", "cancelled_at", "arrival_notified_at")

FORWARD_SQL = "\n".join(
    f"""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'support_ticket'
          AND column_name = '{col}'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE support_ticket
            ALTER COLUMN {col} TYPE timestamp with time zone
            USING {col} AT TIME ZONE 'UTC';
    END IF;
END $$;
"""
    for col in COLUMNS
)

BACKWARD_SQL = "\n".join(
    f"""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'support_ticket'
          AND column_name = '{col}'
          AND data_type = 'timestamp with time zone'
    ) THEN
        ALTER TABLE support_ticket
            ALTER COLUMN {col} TYPE timestamp without time zone
            USING {col} AT TIME ZONE 'UTC';
    END IF;
END $$;
"""
    for col in COLUMNS
)


class Migration(migrations.Migration):

    dependencies = [
        ("drmagdy", "0005_beat_notify_due_arrivals"),
    ]

    operations = [migrations.RunSQL(FORWARD_SQL, BACKWARD_SQL)]
