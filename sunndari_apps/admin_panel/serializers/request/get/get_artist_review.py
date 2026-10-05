from sunndari_apps.admin_panel.serializers.request.get.get_artist_documents import GetArtistDocumentsSerializer


class GetArtistReviewSerializer(GetArtistDocumentsSerializer):
    """Same single required `artist_id` query parameter as the document list."""
