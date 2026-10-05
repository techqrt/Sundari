from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.create_addon import CreateAddOnRequest


class CreateAddOnSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=1)
    duration_minutes = serializers.IntegerField(min_value=0, max_value=480, required=False, default=0)
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False, default=True)
    package_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, max_length=50)

    def create(self, validated_data) -> CreateAddOnRequest:
        return CreateAddOnRequest(**validated_data)
