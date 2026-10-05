from django.db import models
from django.db.models import Q
from django.utils import timezone


class PackageAddOn(models.Model):
    """An extra service an artist sells on top of one or more of their packages. A booking
    snapshots the add-ons it was made with (customers.BookingAddOn), so later edits or
    deletion here never change an existing booking."""

    addon_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='addons',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # Extra time the add-on adds to the appointment (0 = no extra time).
    duration_minutes = models.PositiveIntegerField(default=0)
    packages = models.ManyToManyField('artists.PricingPackage', related_name='addons', blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'package_addons'
        indexes = [models.Index(fields=['artist'])]

    def __str__(self):
        return f"{self.name} (Artist #{self.artist_id})"

    VALUES_FIELDS = (
        'addon_id', 'artist_id', 'name', 'description', 'price', 'duration_minutes',
        'is_active', 'created_at', 'updated_at',
    )

    def create(self, artist_id: int, name: str, price, duration_minutes: int = 0, description: str = None,
               is_active: bool = True, package_ids: list = None) -> int:
        self.artist_id = artist_id
        self.name = name
        self.price = price
        self.duration_minutes = duration_minutes
        self.description = description or None
        self.is_active = is_active
        self.save()
        if package_ids:
            self.packages.set(package_ids)
        return self.addon_id

    @staticmethod
    def update(addon_id: int, name: str = None, price=None, duration_minutes: int = None,
               description: str = None, is_active: bool = None, package_ids: list = None) -> None:
        addon = PackageAddOn.objects.get(addon_id=addon_id)
        if name is not None:
            addon.name = name
        if price is not None:
            addon.price = price
        if duration_minutes is not None:
            addon.duration_minutes = duration_minutes
        if description is not None:
            addon.description = description or None
        if is_active is not None:
            addon.is_active = is_active
        addon.save()
        if package_ids is not None:
            addon.packages.set(package_ids)

    @staticmethod
    def remove(addon_id: int) -> None:
        PackageAddOn.objects.get(addon_id=addon_id).delete()

    @staticmethod
    def with_package_ids(rows: list) -> list:
        """Attaches `package_ids` (list) to each values() row, in one query."""
        links = {}
        for addon_id, package_id in PackageAddOn.packages.through.objects.filter(
            packageaddon_id__in=[row['addon_id'] for row in rows],
        ).order_by('pricingpackage_id').values_list('packageaddon_id', 'pricingpackage_id'):
            links.setdefault(addon_id, []).append(package_id)
        for row in rows:
            row['package_ids'] = links.get(row['addon_id'], [])
        return rows

    @staticmethod
    def get(addon_id: int) -> dict:
        row = PackageAddOn.objects.filter(addon_id=addon_id).values(*PackageAddOn.VALUES_FIELDS).first()
        return PackageAddOn.with_package_ids([row])[0] if row else None

    @staticmethod
    def get_all(
        artist_id: int,
        only_active: bool = False,
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = PackageAddOn.objects.filter(artist_id=artist_id)
        if only_active:
            data = data.filter(is_active=True)
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(Q(name__icontains=search_key) | Q(description__icontains=search_key))
        data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by) if sort_by else data.order_by('addon_id')
        return PackageAddOn.with_package_ids(list(data.values(*PackageAddOn.VALUES_FIELDS)))
