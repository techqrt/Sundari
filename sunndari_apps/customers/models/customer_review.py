from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class CustomerReview(models.Model):
    """An artist's rating of a customer after a completed booking. Deliberately a separate
    table from Review (customer -> artist) so the two directions never mix; one per booking."""

    customer_review_id = models.AutoField(primary_key=True)
    booking = models.OneToOneField(
        'customers.Booking',
        on_delete=models.CASCADE,
        related_name='customer_review',
    )
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='customer_reviews_written',
    )
    customer = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='customer_reviews_received',
    )
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'customer_reviews'
        indexes = [models.Index(fields=['artist']), models.Index(fields=['customer'])]

    def __str__(self):
        return f"CustomerReview #{self.customer_review_id} (Booking #{self.booking_id}, {self.rating}★)"
