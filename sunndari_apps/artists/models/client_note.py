from django.db import models
from django.utils import timezone


class ArtistClientNote(models.Model):
    """The artist's private note about one of their clients. Never shown to the client."""

    note_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey('artists.ArtistProfile', on_delete=models.CASCADE, related_name='client_notes')
    customer = models.ForeignKey('authentication.User', on_delete=models.CASCADE, related_name='artist_notes_about')
    note = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'artist_client_notes'
        unique_together = ('artist', 'customer')

    def __str__(self):
        return f"Note on customer #{self.customer_id} by Artist #{self.artist_id}"
