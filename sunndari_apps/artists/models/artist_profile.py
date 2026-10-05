import os
import uuid

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


def artist_photo_upload_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f'artist_photos/artist_{instance.artist_id}/{uuid.uuid4().hex}{extension}'


class ArtistProfile(models.Model):
    PROFILE_TYPE_CHOICES = [('freelance', 'Freelance'), ('studio', 'Studio')]

    artist_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='artist_profile',
    )
    display_name = models.CharField(max_length=100, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    instagram_url = models.URLField(max_length=300, null=True, blank=True)
    profile_type = models.CharField(max_length=10, choices=PROFILE_TYPE_CHOICES, null=True, blank=True)
    profile_photo = models.FileField(upload_to=artist_photo_upload_path, null=True, blank=True)
    cover_photo = models.FileField(upload_to=artist_photo_upload_path, null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    years_experience = models.PositiveIntegerField(default=0)
    city = models.CharField(max_length=100, null=True, blank=True)
    service_radius_km = models.PositiveIntegerField(default=10)
    # Snapshotted onto each booking (see customers.Booking) — informational for now.
    travel_time_before_minutes = models.PositiveIntegerField(default=0)
    return_buffer_minutes = models.PositiveIntegerField(default=0)
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.PositiveIntegerField(default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    approval_status = models.ForeignKey(
        'core.ApprovalStatus',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    base_address = models.ForeignKey(
        'users.CustomerAddress',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='artist_profiles',
    )
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    # Which version of the Terms + Privacy Policy terms_accepted_at refers to.
    agreement_version = models.CharField(max_length=20, null=True, blank=True)
    # The artist's on/off switch: when False, no new bookings can be made (existing ones are unaffected).
    is_accepting_bookings = models.BooleanField(default=True)
    # Stable, unguessable-enough share handle, created on first request (see ensure_public_slug).
    public_slug = models.SlugField(max_length=80, unique=True, null=True, blank=True)
    profile_view_count = models.PositiveIntegerField(default=0)
    submitted_for_review_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
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
            'artist_id', 'user_id', 'display_name', 'date_of_birth', 'instagram_url', 'profile_type',
            'profile_photo', 'cover_photo', 'travel_time_before_minutes', 'return_buffer_minutes',
            'is_accepting_bookings', 'public_slug', 'profile_view_count', 'agreement_version', 'bio', 'years_experience', 'city',
            'service_radius_km', 'avg_rating', 'total_reviews',
            'commission_rate', 'approval_status_id', 'base_address_id',
            'terms_accepted_at', 'submitted_for_review_at', 'rejection_reason',
            'created_at', 'updated_at',
        ).first()

    @staticmethod
    def update(
        user_id: int,
        bio: str = None,
        years_experience: int = None,
        city: str = None,
        service_radius_km: int = None,
        base_address_id: int = None,
        reset_approval: bool = False,
        display_name: str = None,
        travel_time_before_minutes: int = None,
        return_buffer_minutes: int = None,
        date_of_birth=None,
        instagram_url: str = None,
        profile_type: str = None,
    ) -> None:
        profile = ArtistProfile.objects.get(user_id=user_id)
        if display_name is not None:
            profile.display_name = display_name
        if travel_time_before_minutes is not None:
            profile.travel_time_before_minutes = travel_time_before_minutes
        if return_buffer_minutes is not None:
            profile.return_buffer_minutes = return_buffer_minutes
        if date_of_birth is not None:
            profile.date_of_birth = date_of_birth
        if instagram_url is not None:
            profile.instagram_url = instagram_url
        if profile_type is not None:
            profile.profile_type = profile_type
        if bio is not None:
            profile.bio = bio
        if years_experience is not None:
            profile.years_experience = years_experience
        if city is not None:
            profile.city = city
        if service_radius_km is not None:
            profile.service_radius_km = service_radius_km
        if base_address_id is not None:
            profile.base_address_id = base_address_id
        if reset_approval:
            from sunndari_apps.core.models.approval_status import ApprovalStatus
            pending = ApprovalStatus.objects.filter(name='pending').first()
            profile.approval_status = pending
            profile.submitted_for_review_at = None
        profile.save()

    PHOTO_FIELDS = {'profile': 'profile_photo', 'cover': 'cover_photo'}

    @staticmethod
    def set_photos(user_id: int, profile_photo=None, cover_photo=None) -> None:
        profile = ArtistProfile.objects.get(user_id=user_id)
        replaced = []
        for field, upload in (('profile_photo', profile_photo), ('cover_photo', cover_photo)):
            if upload is None:
                continue
            previous = getattr(profile, field)
            if previous:
                replaced.append((previous.storage, previous.name))
            setattr(profile, field, upload)
        profile.save()
        # Old files are removed only after the new ones are safely saved.
        for storage, name in replaced:
            storage.delete(name)

    @staticmethod
    def remove_photo(user_id: int, kind: str) -> bool:
        profile = ArtistProfile.objects.get(user_id=user_id)
        field = ArtistProfile.PHOTO_FIELDS[kind]
        stored = getattr(profile, field)
        if not stored:
            return False
        storage, name = stored.storage, stored.name
        setattr(profile, field, None)
        profile.save()
        storage.delete(name)
        return True

    @staticmethod
    def accept_agreement(user_id: int) -> None:
        from sunndari.config import Configurations
        ArtistProfile.objects.filter(user_id=user_id).update(
            terms_accepted_at=timezone.now(), agreement_version=Configurations.agreement_version,
        )

    @staticmethod
    def set_accepting_bookings(user_id: int, accepting: bool) -> None:
        ArtistProfile.objects.filter(user_id=user_id).update(is_accepting_bookings=accepting)

    @staticmethod
    def ensure_public_slug(user_id: int) -> str:
        """Returns the artist's share handle, creating it on first use. Never changes once set,
        so shared links keep working."""
        from django.utils.text import slugify
        profile = ArtistProfile.objects.select_related('user').get(user_id=user_id)
        if profile.public_slug:
            return profile.public_slug
        base = slugify(profile.display_name or profile.user.name or 'artist')[:60] or 'artist'
        for _ in range(10):
            candidate = f'{base}-{uuid.uuid4().hex[:6]}'
            if not ArtistProfile.objects.filter(public_slug=candidate).exists():
                profile.public_slug = candidate
                profile.save(update_fields=['public_slug'])
                return candidate
        raise ValueError('Could not allocate a share link, please retry')

    @staticmethod
    def record_view(artist_id: int) -> None:
        # Atomic increment in the database — concurrent views never lose a count.
        ArtistProfile.objects.filter(artist_id=artist_id).update(profile_view_count=models.F('profile_view_count') + 1)

    @staticmethod
    def submit_for_review(user_id: int) -> None:
        # A resubmission after a rejection must re-enter the pending review queue —
        # get_review_queue() only lists approval_status='pending', so leaving it at
        # 'rejected' here would make the artist invisible to admin review forever.
        from sunndari_apps.core.models.approval_status import ApprovalStatus
        pending = ApprovalStatus.objects.filter(name='pending').first()
        ArtistProfile.objects.filter(user_id=user_id).update(
            submitted_for_review_at=timezone.now(),
            approval_status=pending,
            rejection_reason=None,
        )

    @staticmethod
    def approve(artist_id: int) -> None:
        from sunndari_apps.core.models.approval_status import ApprovalStatus
        approved = ApprovalStatus.objects.filter(name='approved').first()
        ArtistProfile.objects.filter(artist_id=artist_id).update(
            approval_status=approved, rejection_reason=None,
        )

    @staticmethod
    def reject(artist_id: int, reason: str = None) -> None:
        from sunndari_apps.core.models.approval_status import ApprovalStatus
        rejected = ApprovalStatus.objects.filter(name='rejected').first()
        ArtistProfile.objects.filter(artist_id=artist_id).update(
            approval_status=rejected, submitted_for_review_at=None, rejection_reason=reason,
        )

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
    def get_review_queue(
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = ArtistProfile.objects.filter(
            submitted_for_review_at__isnull=False,
            approval_status__name='pending',
        )
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(Q(city__icontains=search_key) | Q(bio__icontains=search_key))
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        return list(data.values(
            'artist_id', 'user_id', 'bio', 'years_experience', 'city',
            'service_radius_km', 'approval_status_id', 'submitted_for_review_at', 'created_at',
        ))

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
