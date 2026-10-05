from django.urls import path
from sunndari_apps.artists.controllers.public_profile import PublicArtistController

urlpatterns = [
    path('artists/get/', PublicArtistController.get_public_artist, name='public_get_artist'),
]
