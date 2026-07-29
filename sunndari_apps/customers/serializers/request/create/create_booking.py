from rest_framework import serializers
from sunndari_apps.customers.dataclasses.request.create.create_booking import CreateBookingRequest


class CreateBookingSerializer(serializers.Serializer):
    artist_id = serializers.IntegerField()
    package_id = serializers.IntegerField()
    location_type_id = serializers.IntegerField()
    booking_date = serializers.DateField(input_formats=['%d-%m-%y'])
    start_time = serializers.TimeField()
    address_id = serializers.IntegerField(required=False)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')

    def create(self, validated_data) -> CreateBookingRequest:
        return CreateBookingRequest(**validated_data)
