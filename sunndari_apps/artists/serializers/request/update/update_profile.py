import re
from datetime import date

from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.update_profile import ArtistProfileUpdateRequest


class ArtistProfileUpdateSerializer(serializers.Serializer):
    display_name = serializers.CharField(required=False, max_length=100)
    travel_time_before_minutes = serializers.IntegerField(required=False, min_value=0, max_value=240)
    return_buffer_minutes = serializers.IntegerField(required=False, min_value=0, max_value=240)
    date_of_birth = serializers.DateField(required=False)
    instagram_url = serializers.URLField(required=False, max_length=300)
    profile_type = serializers.ChoiceField(choices=['freelance', 'studio'], required=False)
    bio = serializers.CharField(required=False, allow_blank=True)
    years_experience = serializers.IntegerField(required=False, min_value=0)
    city = serializers.CharField(required=False, max_length=100)
    service_radius_km = serializers.IntegerField(required=False, min_value=1)
    base_address_id = serializers.IntegerField(required=False, allow_null=True)

    MIN_AGE_YEARS = 18
    INSTAGRAM_URL = re.compile(r'^https://(www\.)?instagram\.com/[A-Za-z0-9._]{1,30}/?$')

    def validate_date_of_birth(self, value):
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if value > today or age < self.MIN_AGE_YEARS:
            raise serializers.ValidationError(f'Artist must be at least {self.MIN_AGE_YEARS} years old.')
        if age > 100:
            raise serializers.ValidationError('Invalid date of birth.')
        return value

    def validate_instagram_url(self, value):
        if not self.INSTAGRAM_URL.match(value):
            raise serializers.ValidationError('Must be an https://instagram.com/<handle> profile link.')
        return value

    def create(self, validated_data) -> ArtistProfileUpdateRequest:
        return ArtistProfileUpdateRequest(**validated_data)
