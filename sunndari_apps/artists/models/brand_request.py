from django.db import models
from django.utils import timezone


class BrandRequest(models.Model):
    """An artist asking admins to add a brand that is missing from the list."""

    STATUS_CHOICES = [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')]

    request_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey('artists.ArtistProfile', on_delete=models.CASCADE, related_name='brand_requests')
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    admin_note = models.CharField(max_length=300, null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'brand_requests'
        indexes = [models.Index(fields=['status', 'created_at'])]

    def __str__(self):
        return f"{self.name} ({self.status}) by Artist #{self.artist_id}"
