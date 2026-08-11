from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, phone_number=None, password=None, **extra_fields):
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number=None, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('is_active', True)
        return self.create_user(phone_number=phone_number, password=password, **extra_fields)


class User(AbstractBaseUser):
    ROLE_CHOICES = [
        ('customer', 'Customer'),
        ('artist', 'Artist'),
        ('admin', 'Admin'),
    ]

    user_id = models.AutoField(primary_key=True)
    phone_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    name = models.CharField(max_length=100, default='')
    email = models.EmailField(unique=True, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, null=True, blank=True)
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    access_token = models.TextField(default='')
    refresh_token = models.TextField(default='')
    otp = models.IntegerField(null=True, blank=True)
    otp_expiry = models.DateTimeField(null=True, blank=True)
    otp_attempts = models.IntegerField(default=0)
    lockout_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    fcm_token = models.TextField(null=True, blank=True)
    created_date_time = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['name']

    objects = UserManager()

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.name or 'Unnamed'} ({self.phone_number or self.email or 'No contact'})"

    # ----------------------
    # OTP helpers
    # ----------------------

    def generate_otp(self) -> int:
        import random
        otp = random.randint(100000, 999999)
        self.otp = otp
        self.otp_expiry = timezone.now() + timezone.timedelta(minutes=10)
        self.otp_attempts = 0
        self.save()
        return otp

    def is_locked_out(self) -> bool:
        if self.lockout_until and timezone.now() < self.lockout_until:
            return True
        if self.lockout_until and timezone.now() >= self.lockout_until:
            self.lockout_until = None
            self.otp_attempts = 0
            self.save()
        return False

    def increment_otp_attempts(self) -> None:
        self.otp_attempts += 1
        if self.otp_attempts >= 5:
            self.lockout_until = timezone.now() + timezone.timedelta(minutes=30)
        self.save()

    # ----------------------
    # CRUD
    # ----------------------

    @staticmethod
    def get(user_id: int) -> dict:
        return User.objects.filter(user_id=user_id).values(
            'user_id', 'phone_number', 'name', 'email', 'role',
            'access_token', 'is_active', 'fcm_token', 'created_date_time'
        ).first()

    @staticmethod
    def update(
        user_id: int,
        name: str = None,
        email: str = None,
        phone_number: str = None,
        role: str = None,
        fcm_token: str = None,
    ) -> int:
        user = User.objects.get(user_id=user_id)
        if name is not None:
            user.name = name
        if email is not None:
            user.email = email
        if phone_number is not None:
            user.phone_number = phone_number
        if role is not None:
            user.role = role
        if fcm_token is not None:
            user.fcm_token = fcm_token
        user.save()
        return user.user_id
