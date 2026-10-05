from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.set_specialities import SetSpecialitiesRequest


class SetSpecialitiesSerializer(serializers.Serializer):
    sub_category_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True, max_length=10,
    )

    def create(self, validated_data) -> SetSpecialitiesRequest:
        return SetSpecialitiesRequest(**validated_data)
