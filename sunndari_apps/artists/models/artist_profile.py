from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


class ArtistProfile(models.Model):
    artist_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='artist_profile',
    )
    bio = models.TextField(null=True, blank=True)
    years_experience = models.PositiveIntegerField(default=0)
    city = models.CharField(max_length=100, null=True, blank=True)
    service_radius_km = models.PositiveIntegerField(default=10)
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.PositiveIntegerField(default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    approval_status = models.ForeignKey(
        'core.ApprovalStatus',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'artist_profiles'

    def __str__(self):
        return f"Artist #{self.artist_id} ({self.user_id})"

    @staticmethod
    def create_for_user(user_id: int) -> 'ArtistProfile':
        from sunndari_apps.core.models.approval_status import ApprovalStatus
        pending_status = ApprovalStatus.objects.filter(name='pending').first()
        return ArtistProfile.objects.create(
            user_id=user_id,
            approval_status=pending_status,
        )

    @staticmethod
    def get(artist_id: int = None, user_id: int = None) -> dict:
        qs = ArtistProfile.objects
        if artist_id:
            qs = qs.filter(artist_id=artist_id)
        elif user_id:
            qs = qs.filter(user_id=user_id)
        else:
            return None
        return qs.values(
            'artist_id', 'user_id', 'bio', 'years_experience', 'city',
            'service_radius_km', 'avg_rating', 'total_reviews',
            'commission_rate', 'approval_status_id', 'created_at', 'updated_at',
        ).first()

    @staticmethod
    def update(
        user_id: int,
        bio: str = None,
        years_experience: int = None,
        city: str = None,
        service_radius_km: int = None,
        reset_approval: bool = False,
    ) -> None:
        profile = ArtistProfile.objects.get(user_id=user_id)
        if bio is not None:
            profile.bio = bio
        if years_experience is not None:
            profile.years_experience = years_experience
        if city is not None:
            profile.city = city
        if service_radius_km is not None:
            profile.service_radius_km = service_radius_km
        if reset_approval:
            from sunndari_apps.core.models.approval_status import ApprovalStatus
            pending = ApprovalStatus.objects.filter(name='pending').first()
            profile.approval_status = pending
        profile.save()

    @staticmethod
    def record_review(artist_id: int, rating: int) -> None:
        with transaction.atomic():
            profile = ArtistProfile.objects.select_for_update().get(artist_id=artist_id)
            new_total = profile.total_reviews + 1
            new_avg = ((profile.avg_rating * profile.total_reviews) + rating) / new_total
            profile.avg_rating = round(new_avg, 2)
            profile.total_reviews = new_total
            profile.save()

    @staticmethod
    def get_all(
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = ArtistProfile.objects.all()
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(Q(city__icontains=search_key) | Q(bio__icontains=search_key))
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        return list(data.values(
            'artist_id', 'user_id', 'bio', 'years_experience', 'city',
            'service_radius_km', 'avg_rating', 'total_reviews',
            'commission_rate', 'approval_status_id', 'created_at', 'updated_at',
        ))
