from django.db import models
from django.db.models import Q
from django.utils import timezone
from sunndari_apps.authentication.models import User


class CustomerAddress(models.Model):
    address_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100)
    pin_code = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customer_addresses'

    def __str__(self):
        return f"{self.address_line_1}, {self.city} ({self.user_id})"

    # ----------------------
    # CRUD
    # ----------------------

    def create(
        self,
        user_id: int,
        address_line_1: str,
        city: str,
        pin_code: str,
        address_line_2: str = None,
        is_default: bool = False,
    ) -> int:
        if is_default:
            CustomerAddress.objects.filter(user_id=user_id).update(is_default=False)
        self.user_id = user_id
        self.address_line_1 = address_line_1
        self.address_line_2 = address_line_2
        self.city = city
        self.pin_code = pin_code
        self.is_default = is_default
        self.save()
        return self.address_id

    @staticmethod
    def update(
        address_id: int,
        address_line_1: str = None,
        address_line_2: str = None,
        city: str = None,
        pin_code: str = None,
        is_default: bool = None,
        user_id: int = None,
    ) -> int:
        address = CustomerAddress.objects.get(address_id=address_id)
        if is_default:
            CustomerAddress.objects.filter(user_id=address.user_id).update(is_default=False)
        if address_line_1 is not None:
            address.address_line_1 = address_line_1
        if address_line_2 is not None:
            address.address_line_2 = address_line_2
        if city is not None:
            address.city = city
        if pin_code is not None:
            address.pin_code = pin_code
        if is_default is not None:
            address.is_default = is_default
        address.save()
        return address.address_id

    @staticmethod
    def remove(address_id: int) -> None:
        CustomerAddress.objects.get(address_id=address_id).delete()

    @staticmethod
    def get(address_id: int) -> dict:
        return CustomerAddress.objects.filter(address_id=address_id).values(
            'address_id', 'user_id', 'address_line_1', 'address_line_2',
            'city', 'pin_code', 'is_default', 'created_at', 'updated_at'
        ).first()

    @staticmethod
    def get_all(
        user_id: int,
        sort_by: str = '',
        sort_order: str = '',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = CustomerAddress.objects.filter(user_id=user_id)
        if filter_key and filter_value:
            data = data.filter(**{f'{filter_key}__icontains': filter_value})
        if search_key:
            data = data.filter(
                Q(address_line_1__icontains=search_key) |
                Q(city__icontains=search_key) |
                Q(pin_code__icontains=search_key)
            )
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        return list(data.values(
            'address_id', 'user_id', 'address_line_1', 'address_line_2',
            'city', 'pin_code', 'is_default', 'created_at', 'updated_at'
        ))

    @staticmethod
    def count_for_user(user_id: int) -> int:
        return CustomerAddress.objects.filter(user_id=user_id).count()
