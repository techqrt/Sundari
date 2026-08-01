from rest_framework import serializers
from sunndari_apps.authentication.models import User


# ─── Phone OTP ────────────────────────────────────────────────────────────────

class PhoneOTPRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)
    role = serializers.ChoiceField(
        choices=[c[0] for c in User.ROLE_CHOICES],
        required=False,
    )

    def validate(self, data):
        if not data.get('phone_number'):
            raise serializers.ValidationError({'phone_number': 'Phone number is required.'})
        return data


class PhoneOTPVerifySerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)
    otp = serializers.CharField(max_length=6)

    def validate(self, data):
        otp = data.get('otp', '')
        if not otp.isdigit() or len(otp) != 6:
            raise serializers.ValidationError({'otp': 'OTP must be exactly 6 digits.'})
        return data


# ─── Email OTP ────────────────────────────────────────────────────────────────

class EmailOTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=[c[0] for c in User.ROLE_CHOICES],
        required=False,
    )


class EmailOTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

    def validate(self, data):
        otp = data.get('otp', '')
        if not otp.isdigit() or len(otp) != 6:
            raise serializers.ValidationError({'otp': 'OTP must be exactly 6 digits.'})
        return data


# ─── Username / Password ──────────────────────────────────────────────────────

class RegisterWithPasswordSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(max_length=20, required=False)
    password = serializers.CharField(min_length=8, write_only=True)
    role = serializers.ChoiceField(choices=[c[0] for c in User.ROLE_CHOICES])

    def validate(self, data):
        if not data.get('email') and not data.get('phone_number'):
            raise serializers.ValidationError('Either email or phone number is required.')
        return data


class LoginWithPasswordSerializer(serializers.Serializer):
    username = serializers.CharField(help_text='Email or phone number')
    password = serializers.CharField(write_only=True)


# ─── Google ───────────────────────────────────────────────────────────────────

class GoogleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField()
    role = serializers.ChoiceField(
        choices=[c[0] for c in User.ROLE_CHOICES],
        required=False,
    )


# ─── Token Refresh ────────────────────────────────────────────────────────────

class TokenRefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


# ─── Response (Swagger only) ──────────────────────────────────────────────────

class AuthResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField(allow_null=True, allow_blank=True)
    phone_number = serializers.CharField(allow_null=True, allow_blank=True)
    role = serializers.CharField(allow_null=True, allow_blank=True)
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
