from rest_framework import serializers
from sunndari_apps.customers.dataclasses.request.create.create_booking import CreateBookingRequest


class CreateBookingSerializer(serializers.Serializer):
    artist_id = serializers.IntegerField()
    package_id = serializers.IntegerField()
    location_type_id = serializers.IntegerField()
    booking_date = serializers.DateField(input_formats=['%d-%m-%y'])
    start_time = serializers.TimeField()
    # Home Visit and On-Site Event need address_id; In-Salon needs salon_address_id instead (checked against the
    # booking type in the view, which is where the type is known).
    address_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    salon_address_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')
    addon_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, max_length=10)

    def create(self, validated_data) -> CreateBookingRequest:
        return CreateBookingRequest(**validated_data)
