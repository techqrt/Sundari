from rest_framework import serializers
from sunndari.constants import Constants
from sunndari_apps.artists.dataclasses.request.update.update_service_area import UpdateServiceAreaRequest


class UpdateServiceAreaSerializer(serializers.Serializer):
    area_id = serializers.IntegerField()
    city = serializers.CharField(max_length=100, required=False)
    travel_charge_type = serializers.ChoiceField(choices=['free', 'per_visit', 'per_km'], required=False)
    charge_amount = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=0, max_value=100000, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate(self, data):
        if data.get('travel_charge_type') == 'per_km':
            raise serializers.ValidationError({'travel_charge_type': Constants.per_km_unavailable})
        return data

    def create(self, validated_data) -> UpdateServiceAreaRequest:
        return UpdateServiceAreaRequest(**validated_data)
