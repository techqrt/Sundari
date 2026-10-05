from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.get.get_share_link import GetShareLinkRequest


class GetShareLinkSerializer(serializers.Serializer):
    def create(self, validated_data) -> GetShareLinkRequest:
        return GetShareLinkRequest(**validated_data)
