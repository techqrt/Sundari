from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.update_profile import ArtistProfileUpdateRequest


class ArtistProfileUpdateSerializer(serializers.Serializer):
    bio = serializers.CharField(required=False, allow_blank=True)
    years_experience = serializers.IntegerField(required=False, min_value=0)
    city = serializers.CharField(required=False, max_length=100)
    service_radius_km = serializers.IntegerField(required=False, min_value=1)

    def create(self, validated_data) -> ArtistProfileUpdateRequest:
        return ArtistProfileUpdateRequest(**validated_data)
