from django.db import migrations


class Migration(migrations.Migration):
    """State-only: Payment moves from customers to the payments app (see
    payments/migrations/0001_initial.py). No database_operations here — the physical
    'payments' table and its data are untouched, this only updates Django's migration
    state so customers no longer claims to own that model."""

    dependencies = [
        ('customers', '0004_booking_lifecycle_credentials'),
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='Payment'),
            ],
            database_operations=[],
        ),
    ]
