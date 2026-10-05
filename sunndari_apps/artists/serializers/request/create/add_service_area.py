from rest_framework import serializers
from sunndari.constants import Constants
from sunndari_apps.artists.dataclasses.request.create.add_service_area import AddServiceAreaRequest


class AddServiceAreaSerializer(serializers.Serializer):
    city = serializers.CharField(max_length=100)
    travel_charge_type = serializers.ChoiceField(choices=['free', 'per_visit', 'per_km'])
    charge_amount = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=0, max_value=100000, required=False)

    def validate(self, data):
        charge_type = data.get('travel_charge_type')
        amount = data.get('charge_amount')
        if charge_type == 'per_km':
            raise serializers.ValidationError({'travel_charge_type': Constants.per_km_unavailable})
        if charge_type == 'free' and amount:
            raise serializers.ValidationError({'charge_amount': 'charge_amount must be empty or 0 for free travel.'})
        if charge_type == 'per_visit' and not amount:
            raise serializers.ValidationError({'charge_amount': 'charge_amount is required for a per-visit charge.'})
        return data

    def create(self, validated_data) -> AddServiceAreaRequest:
        return AddServiceAreaRequest(**validated_data)
