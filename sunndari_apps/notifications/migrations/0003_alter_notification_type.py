from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_alter_notification_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='type',
            field=models.CharField(choices=[('booking_confirmed', 'Booking Confirmed'), ('booking_reminder_24h', 'Booking Reminder — 24hr'), ('booking_reminder_2h', 'Booking Reminder — 2hr'), ('payment_status', 'Payment Status Change'), ('new_booking_alert', 'New Booking Alert'), ('booking_cancelled', 'Booking Cancelled'), ('booking_completed', 'Booking Completed'), ('booking_no_show', 'Booking No-Show'), ('help_center_customer_message', 'Help Center — Customer Message'), ('help_center_admin_reply', 'Help Center — Admin Reply'), ('generic', 'Generic')], default='generic', max_length=30),
        ),
    ]
