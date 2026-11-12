from django.db import migrations, models


def switch_off_ineligible(apps, schema_editor):
    """Bookings default to OFF for artists who are not eligible to take them: not exempt and with no completed,
    un-voided registration payment. Artists who are exempt (everyone approved before the fee existed) or who have
    paid keep their current setting, so nothing changes for the artists customers can see today. The artists this
    switches off were already hidden from customers (none of them is approved and exempt or paid)."""
    ArtistProfile = apps.get_model('artists', 'ArtistProfile')
    ArtistRegistrationPayment = apps.get_model('artists', 'ArtistRegistrationPayment')
    paid_artist_ids = ArtistRegistrationPayment.objects.filter(
        paid_at__isnull=False, refund_requested_at__isnull=True,
    ).values('artist_id')
    ArtistProfile.objects.filter(
        registration_fee_exempt=False, is_accepting_bookings=True,
    ).exclude(artist_id__in=paid_artist_ids).update(is_accepting_bookings=False)


class Migration(migrations.Migration):

    dependencies = [
        ('artists', '0021_registration_completed_excludes_voided'),
    ]

    operations = [
        migrations.AddField(
            model_name='artistprofile',
            name='accepting_locked_by_admin',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(switch_off_ineligible, migrations.RunPython.noop),
    ]
