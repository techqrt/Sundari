import os
import uuid

from django.db import models, transaction
from django.db.models import Exists, OuterRef, Q
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
    service_radius_km = models.PositiveIntegerField(default=50)
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
    portfolio_approval_status = models.BooleanField(default=False)
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
    # Set when an admin switches bookings off: the artist cannot switch them back on; only an admin can.
    accepting_locked_by_admin = models.BooleanField(default=False)
    # Artists approved before the registration fee existed, or waived by an admin, do not have to pay it.
    registration_fee_exempt = models.BooleanField(default=False)
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
        # A new artist starts with bookings OFF: paying the registration fee only makes them eligible to
        # switch it on, it never switches it on for them.
        return ArtistProfile.objects.create(
            user_id=user_id,
            approval_status=pending_status,
            is_accepting_bookings=False,
        )

    @staticmethod
    def eligible_filter(prefix: str = '') -> Q:
        """The registration-payment condition for use in a query: exempt, or holding a completed registration
        payment that has not been voided or refunded. The same test as is_eligible(), as a filter. The payment
        subquery refers to the artist through `artist_id`, which is a column of ArtistProfile and of any model
        with an `artist` foreign key (e.g. PricingPackage), so it works inside a filter on either; `prefix` is
        only the path to the artist's exempt flag, e.g. 'artist__'."""
        from sunndari_apps.artists.models.registration_payment import ArtistRegistrationPayment
        paid = Exists(ArtistRegistrationPayment.objects.filter(
            artist_id=OuterRef('artist_id'), paid_at__isnull=False, refund_requested_at__isnull=True,
        ))
        return Q(**{f'{prefix}registration_fee_exempt': True}) | Q(paid)

    @staticmethod
    def public_filter(prefix: str = '') -> Q:
        """What a customer may see and book: approved by an admin, registration payment settled (or exempt),
        bookings switched ON, and not switched off by an admin. These are separate facts that are only combined
        here, at read time, so a refund or an admin switching bookings off takes effect at once everywhere this
        filter is used. The admin lock is checked on its own rather than left to "locked implies OFF": if the two
        ever disagree (a race between the artist's switch and an admin's, or a stray edit) the admin's decision
        still wins. `prefix` is the path to the artist, e.g. 'artist__' when querying PricingPackage."""
        return (
            Q(**{f'{prefix}approval_status__name': 'approved', f'{prefix}is_accepting_bookings': True,
                 f'{prefix}accepting_locked_by_admin': False})
            & ArtistProfile.eligible_filter(prefix)
        )

    @staticmethod
    def is_public(artist_id: int) -> bool:
        """Whether customers may see this artist at all (see public_filter)."""
        return ArtistProfile.objects.filter(ArtistProfile.public_filter(), artist_id=artist_id).exists()

    @staticmethod
    def is_eligible(artist_id: int) -> bool:
        """Whether this artist may switch bookings ON as far as payment goes: exempt, or a completed,
        un-voided registration payment. Approval is a separate check."""
        from sunndari_apps.artists.registration_fee import RegistrationFee
        return (
            ArtistProfile.objects.filter(artist_id=artist_id, registration_fee_exempt=True).exists()
            or RegistrationFee.is_paid(artist_id)
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
            'is_accepting_bookings', 'accepting_locked_by_admin', 'public_slug', 'profile_view_count', 'agreement_version', 'bio', 'years_experience', 'city',
            'service_radius_km', 'avg_rating', 'total_reviews',
            'commission_rate', 'approval_status_id', 'portfolio_approval_status', 'base_address_id',
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
    def _cannot_take_bookings_reason(profile: 'ArtistProfile'):
        """Why this artist may not take bookings (ignoring their own ON/OFF switch), or None: not approved or
        suspended, switched off by an admin, or the registration payment is not settled. In that order, so the
        message names the cause the artist cannot fix by paying."""
        from sunndari.constants import Constants
        approval_name = profile.approval_status.name if profile.approval_status else None
        if approval_name == 'suspended':
            return Constants.artist_suspended
        if approval_name != 'approved':
            return Constants.accepting_requires_approval
        if profile.accepting_locked_by_admin:
            return Constants.accepting_locked_by_admin
        if not ArtistProfile.is_eligible(profile.artist_id):
            return Constants.accepting_requires_payment
        return None

    @staticmethod
    def accept_block_reason(artist_id: int):
        """Why this artist may not accept a booking request right now, or None. Checked when an artist confirms a
        request (the only way a booking becomes confirmed), so the switch cannot be bypassed with a direct call.
        Declining, cancelling, starting and completing are not checked: existing bookings are never affected."""
        from sunndari.constants import Constants
        profile = ArtistProfile.objects.select_related('approval_status').filter(artist_id=artist_id).first()
        if profile is None:
            return Constants.artist_not_found
        reason = ArtistProfile._cannot_take_bookings_reason(profile)
        if reason:
            return reason
        if not profile.is_accepting_bookings:
            return Constants.accepting_off_cannot_confirm
        return None

    @staticmethod
    def set_accepting_bookings(user_id: int, accepting: bool) -> None:
        """The artist's own switch. OFF is always allowed. ON needs, in this order: not suspended and approved, not
        switched off by an admin, and registration payment settled (or exempt); otherwise a ValueError saying which.
        Done under a row lock so it cannot race an admin's change or a refund."""
        with transaction.atomic():
            profile = ArtistProfile.objects.select_for_update().select_related('approval_status').get(user_id=user_id)
            if accepting:
                reason = ArtistProfile._cannot_take_bookings_reason(profile)
                if reason:
                    raise ValueError(reason)
            profile.is_accepting_bookings = accepting
            profile.save(update_fields=['is_accepting_bookings', 'updated_at'])

    @staticmethod
    def admin_set_accepting_bookings(artist_id: int, accepting: bool) -> tuple:
        """An admin's switch. OFF always works and sets the lock, so the artist cannot switch bookings back on
        themselves. ON needs the artist to be approved and payment-eligible (an admin cannot get around the fee),
        and clears the lock. Returns (profile, changed), `changed` being False for a repeat request."""
        from sunndari.constants import Constants
        with transaction.atomic():
            profile = ArtistProfile.objects.select_for_update().select_related('approval_status').filter(
                artist_id=artist_id,
            ).first()
            if profile is None:
                raise ValueError(Constants.artist_not_found)
            if accepting:
                approval_name = profile.approval_status.name if profile.approval_status else None
                if approval_name == 'suspended':
                    raise ValueError(Constants.artist_suspended)
                if approval_name != 'approved':
                    raise ValueError(Constants.admin_accepting_requires_approval)
                if not ArtistProfile.is_eligible(profile.artist_id):
                    raise ValueError(Constants.admin_accepting_requires_payment)
            locked = not accepting
            changed = profile.is_accepting_bookings != accepting or profile.accepting_locked_by_admin != locked
            if changed:
                profile.is_accepting_bookings = accepting
                profile.accepting_locked_by_admin = locked
                profile.save(update_fields=['is_accepting_bookings', 'accepting_locked_by_admin', 'updated_at'])
            return profile, changed

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
        # Bookings go OFF too, so re-approving later (or paying again) never switches them back on by itself.
        ArtistProfile.objects.filter(artist_id=artist_id).update(
            approval_status=rejected, submitted_for_review_at=None, rejection_reason=reason,
            is_accepting_bookings=False,
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
