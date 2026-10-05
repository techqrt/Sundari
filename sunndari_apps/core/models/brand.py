from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Brand(models.Model):
    """Admin-managed list of makeup/beauty brands artists can name in their packages."""

    brand_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'brands'
        constraints = [models.UniqueConstraint(Lower('name'), name='unique_brand_name_ci')]
        ordering = ['name']

    def __str__(self):
        return self.name

    @staticmethod
    def name_exists(name: str, exclude_brand_id: int = None) -> bool:
        qs = Brand.objects.filter(name__iexact=name.strip())
        if exclude_brand_id:
            qs = qs.exclude(brand_id=exclude_brand_id)
        return qs.exists()
