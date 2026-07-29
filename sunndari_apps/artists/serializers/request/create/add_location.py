from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.add_location import AddLocationRequest


class AddLocationSerializer(serializers.Serializer):
    location_type_id = serializers.IntegerField()

    def create(self, validated_data) -> AddLocationRequest:
        return AddLocationRequest(**validated_data)
