from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.update_addon import UpdateAddOnRequest


class UpdateAddOnSerializer(serializers.Serializer):
    addon_id = serializers.IntegerField()
    name = serializers.CharField(max_length=200, required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=1, required=False)
    duration_minutes = serializers.IntegerField(min_value=0, max_value=480, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    package_ids = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True, max_length=50)

    def create(self, validated_data) -> UpdateAddOnRequest:
        return UpdateAddOnRequest(**validated_data)
