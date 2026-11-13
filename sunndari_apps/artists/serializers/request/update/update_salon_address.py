from rest_framework import serializers

from sunndari.constants import Constants
from sunndari_apps.artists.dataclasses.request.update.update_salon_address import UpdateSalonAddressRequest
from sunndari_apps.artists.serializers.request.create.create_salon_address import CreateSalonAddressSerializer, SalonTextField

EDITABLE_FIELDS = ('name', 'address_line_1', 'address_line_2', 'city', 'pin_code', 'latitude', 'longitude')


class UpdateSalonAddressSerializer(serializers.Serializer):
    """Send salon_address_id and only the fields to change; the rest are kept. Same rules as adding an address."""
    salon_address_id = serializers.IntegerField()
    name = SalonTextField(max_length=100, required=False)
    address_line_1 = SalonTextField(max_length=255, required=False)
    address_line_2 = SalonTextField(max_length=255, required=False, allow_blank=True, allow_null=True)
    city = SalonTextField(max_length=100, required=False)
    pin_code = SalonTextField(max_length=10, required=False)
    latitude = serializers.DecimalField(max_digits=None, decimal_places=None, min_value=-90, max_value=90, required=False)
    longitude = serializers.DecimalField(max_digits=None, decimal_places=None, min_value=-180, max_value=180, required=False)

    def validate_latitude(self, value):
        return CreateSalonAddressSerializer._six_places(value)

    def validate_longitude(self, value):
        return CreateSalonAddressSerializer._six_places(value)

    def validate(self, data):
        if not any(field in data for field in EDITABLE_FIELDS):
            raise serializers.ValidationError(Constants.salon_nothing_to_update)
        return data

    def create(self, validated_data) -> UpdateSalonAddressRequest:
        provided = tuple(field for field in EDITABLE_FIELDS if field in validated_data)
        return UpdateSalonAddressRequest(**validated_data, provided=provided)
