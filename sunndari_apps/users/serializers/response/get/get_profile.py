from rest_framework import serializers


class UserProfileGetSerializer(serializers.Serializer):
    userId = serializers.IntegerField()
    # A phone/Google sign-up has no name until the user sets one (model default is '').
    name = serializers.CharField(allow_blank=True)
    role = serializers.CharField(allow_null=True, allow_blank=True)
    # Present only when you view your own profile (or you are an admin); see UserProfileView.
    email = serializers.EmailField(allow_null=True, allow_blank=True, required=False)
    phoneNumber = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    isActive = serializers.BooleanField(required=False)
    fcmToken = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    createdAt = serializers.DateTimeField(required=False)


class UserProfileResponseGetSerializer(serializers.Serializer):
    data = UserProfileGetSerializer()
