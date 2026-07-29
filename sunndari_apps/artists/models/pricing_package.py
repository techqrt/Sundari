from django.db import models
from django.db.models import Q
from django.utils import timezone


class PricingPackage(models.Model):
    package_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='pricing_packages',
    )
    sub_category = models.ForeignKey(
        'core.ServiceSubCategory',
        on_delete=models.PROTECT,
        related_name='pricing_packages',
    )
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_minutes = models.PositiveIntegerField()
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pricing_packages'

    def __str__(self):
        return f"{self.name} (Artist #{self.artist_id})"

    @staticmethod
    def get(package_id: int) -> dict:
        return PricingPackage.objects.filter(package_id=package_id).values(
            'package_id', 'artist_id', 'sub_category_id', 'name',
            'price', 'duration_minutes', 'description', 'is_active', 'created_at', 'updated_at',
        ).first()

    def create(self, artist_id: int, sub_category_id: int, name: str, price, duration_minutes: int, description: str = None) -> int:
        self.artist_id = artist_id
        self.sub_category_id = sub_category_id
        self.name = name
        self.price = price
        self.duration_minutes = duration_minutes
        self.description = description
        self.save()
        return self.package_id

    @staticmethod
    def update(package_id: int, name: str = None, price=None, duration_minutes: int = None, description: str = None, sub_category_id: int = None, is_active: bool = None) -> None:
        pkg = PricingPackage.objects.get(package_id=package_id)
        if name is not None:
            pkg.name = name
        if price is not None:
            pkg.price = price
        if duration_minutes is not None:
            pkg.duration_minutes = duration_minutes
        if description is not None:
            pkg.description = description
        if sub_category_id is not None:
            pkg.sub_category_id = sub_category_id
        if is_active is not None:
            pkg.is_active = is_active
        pkg.save()

    @staticmethod
    def remove(package_id: int) -> None:
        PricingPackage.objects.get(package_id=package_id).delete()

    @staticmethod
    def get_all(
        artist_id: int,
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = PricingPackage.objects.filter(artist_id=artist_id)
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(Q(name__icontains=search_key) | Q(description__icontains=search_key))
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        return list(data.values(
            'package_id', 'artist_id', 'sub_category_id', 'name',
            'price', 'duration_minutes', 'description', 'is_active', 'created_at', 'updated_at',
        ))

    @staticmethod
    def active_count(artist_id: int) -> int:
        return PricingPackage.objects.filter(artist_id=artist_id, is_active=True).count()
