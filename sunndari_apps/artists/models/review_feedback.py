from django.db import models
from django.utils import timezone


class ArtistReviewFeedback(models.Model):
    """Append-only history of admin decisions on an artist's page review. The latest row
    mirrors ArtistProfile.rejection_reason (kept for compatibility); earlier rows are never
    overwritten, so the artist can see every round of feedback."""

    DECISION_CHOICES = [('approved', 'Approved'), ('rejected', 'Rejected')]

    feedback_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='review_feedback',
    )
    admin_user = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='artist_review_feedback_given',
    )
    decision = models.CharField(max_length=10, choices=DECISION_CHOICES)
    message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'artist_review_feedback'
        indexes = [models.Index(fields=['artist', '-created_at'])]

    def __str__(self):
        return f"Feedback #{self.feedback_id} ({self.decision}) for Artist #{self.artist_id}"

    @staticmethod
    def record(artist_id: int, admin_user_id: int, decision: str, message: str = '') -> int:
        return ArtistReviewFeedback.objects.create(
            artist_id=artist_id, admin_user_id=admin_user_id, decision=decision, message=message or '',
        ).feedback_id

    @staticmethod
    def get_latest(artist_id: int):
        return ArtistReviewFeedback.objects.filter(artist_id=artist_id).order_by('-created_at', '-feedback_id').values(
            'feedback_id', 'decision', 'message', 'created_at',
        ).first()

    @staticmethod
    def get_all(artist_id: int, sort_order: str = 'asc') -> list:
        prefix = '-' if sort_order == 'desc' else ''
        return list(
            ArtistReviewFeedback.objects.filter(artist_id=artist_id)
            .order_by(f'{prefix}created_at', f'{prefix}feedback_id')
            .values('feedback_id', 'decision', 'message', 'created_at')
        )
