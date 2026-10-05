from rest_framework import serializers


class AddOnSerializer(serializers.Serializer):
    addOnId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True, allow_blank=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    durationMinutes = serializers.IntegerField()
    isActive = serializers.BooleanField()
    packageIds = serializers.ListField(child=serializers.IntegerField())
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class AddOnResponseSerializer(serializers.Serializer):
    data = AddOnSerializer()
