from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.add_service import AddServiceRequest


class AddServiceSerializer(serializers.Serializer):
    sub_category_id = serializers.IntegerField()
    custom_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    custom_duration_minutes = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def create(self, validated_data) -> AddServiceRequest:
        return AddServiceRequest(**validated_data)
