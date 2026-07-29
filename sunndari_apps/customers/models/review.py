from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class Review(models.Model):
    review_id = models.AutoField(primary_key=True)
    booking = models.OneToOneField(
        'customers.Booking',
        on_delete=models.CASCADE,
        related_name='review',
    )
    customer = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='reviews_as_customer',
    )
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviews'
        indexes = [
            models.Index(fields=['artist']),
        ]

    def __str__(self):
        return f"Review #{self.review_id} (Booking #{self.booking_id}, {self.rating}★)"

    VALUES_FIELDS = (
        'review_id', 'booking_id', 'customer_id', 'artist_id',
        'rating', 'comment', 'created_at', 'updated_at',
    )

    def create(self, booking_id: int, customer_id: int, artist_id: int, rating: int, comment: str = None) -> int:
        self.booking_id = booking_id
        self.customer_id = customer_id
        self.artist_id = artist_id
        self.rating = rating
        self.comment = comment
        self.save()
        return self.review_id

    @staticmethod
    def get(review_id: int) -> dict:
        return Review.objects.filter(review_id=review_id).values(*Review.VALUES_FIELDS).first()

    @staticmethod
    def exists_for_booking(booking_id: int) -> bool:
        return Review.objects.filter(booking_id=booking_id).exists()

    @staticmethod
    def get_all(
        artist_id: int = None,
        customer_id: int = None,
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = Review.objects.all()
        if artist_id:
            data = data.filter(artist_id=artist_id)
        if customer_id:
            data = data.filter(customer_id=customer_id)
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(comment__icontains=search_key)
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        else:
            data = data.order_by('-created_at')
        return list(data.values(*Review.VALUES_FIELDS))
