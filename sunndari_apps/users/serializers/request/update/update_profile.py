from rest_framework import serializers
from sunndari_apps.users.dataclasses.request.update.update_profile import UserProfileUpdateRequest


class UserProfileUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False, allow_null=True)
    email = serializers.EmailField(required=False, allow_null=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_null=True)

    def create(self, validated_data) -> UserProfileUpdateRequest:
        return UserProfileUpdateRequest(**validated_data)
