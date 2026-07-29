from django.db import models
from django.db.models import Q
from django.utils import timezone


class ServiceCategory(models.Model):
    category_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'service_categories'

    def __str__(self):
        return self.name

    @staticmethod
    def get(category_id: int) -> dict:
        return ServiceCategory.objects.filter(category_id=category_id).values(
            'category_id', 'name', 'description', 'is_active', 'created_at', 'updated_at'
        ).first()

    @staticmethod
    def get_all(
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = ServiceCategory.objects.all()
        if filter_key and filter_value:
            data = data.filter(**{f'{filter_key}__icontains': filter_value})
        if search_key:
            data = data.filter(Q(name__icontains=search_key) | Q(description__icontains=search_key))
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        return list(data.values('category_id', 'name', 'description', 'is_active', 'created_at', 'updated_at'))
