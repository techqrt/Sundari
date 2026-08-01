from rest_framework import serializers


class UserProfileGetSerializer(serializers.Serializer):
    userId = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField(allow_null=True, allow_blank=True)
    phoneNumber = serializers.CharField(allow_null=True, allow_blank=True)
    role = serializers.CharField(allow_null=True, allow_blank=True)
    isActive = serializers.BooleanField()
    createdAt = serializers.DateTimeField()


class UserProfileResponseGetSerializer(serializers.Serializer):
    data = UserProfileGetSerializer()
