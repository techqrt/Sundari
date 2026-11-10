from django.db import migrations


def exempt_approved(apps, schema_editor):
    """Artists approved before the registration fee existed do not have to pay it."""
    ArtistProfile = apps.get_model('artists', 'ArtistProfile')
    ArtistProfile.objects.filter(approval_status__name='approved').update(registration_fee_exempt=True)


class Migration(migrations.Migration):

    dependencies = [
        ('artists', '0018_artist_registration_fee_and_promo_codes'),
    ]

    operations = [
        migrations.RunPython(exempt_approved, migrations.RunPython.noop),
    ]
