from dataclasses import dataclass
from rest_framework import serializers


@dataclass
class RequestContactChangeRequest:
    email: str = None
    phone_number: str = None
    user_id: int = None


@dataclass
class VerifyContactChangeRequest:
    otp: str = None
    user_id: int = None


class RequestContactChangeSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(max_length=20, required=False)

    def validate(self, data):
        if bool(data.get('email')) == bool(data.get('phone_number')):
            raise serializers.ValidationError('Provide exactly one of email or phone_number.')
        return data

    def create(self, validated_data) -> RequestContactChangeRequest:
        return RequestContactChangeRequest(**validated_data)


class VerifyContactChangeSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)

    def validate_otp(self, value):
        if not value.isdigit() or len(value) != 6:
            raise serializers.ValidationError('OTP must be exactly 6 digits.')
        return value

    def create(self, validated_data) -> VerifyContactChangeRequest:
        return VerifyContactChangeRequest(**validated_data)
