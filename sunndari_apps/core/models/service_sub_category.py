from django.db import models
from django.db.models import Q
from django.utils import timezone


class ServiceSubCategory(models.Model):
    sub_category_id = models.AutoField(primary_key=True)
    category = models.ForeignKey(
        'core.ServiceCategory',
        on_delete=models.CASCADE,
        related_name='sub_categories',
    )
    name = models.CharField(max_length=150)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'service_sub_categories'
        unique_together = ('category', 'name')

    def __str__(self):
        return f"{self.category.name} → {self.name}"

    @staticmethod
    def get(sub_category_id: int) -> dict:
        return ServiceSubCategory.objects.filter(sub_category_id=sub_category_id).values(
            'sub_category_id', 'category_id', 'name', 'description', 'is_active', 'created_at', 'updated_at'
        ).first()

    @staticmethod
    def get_all(
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = ServiceSubCategory.objects.all()
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(Q(name__icontains=search_key) | Q(description__icontains=search_key))
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        return list(data.values(
            'sub_category_id', 'category_id', 'name', 'description', 'is_active', 'created_at', 'updated_at'
        ))
