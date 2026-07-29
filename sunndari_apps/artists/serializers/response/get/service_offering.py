from rest_framework import serializers


class ServiceOfferingSerializer(serializers.Serializer):
    offeringId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    subCategoryId = serializers.IntegerField()
    customPrice = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    customDurationMinutes = serializers.IntegerField(allow_null=True)
    isActive = serializers.BooleanField()
    createdAt = serializers.DateTimeField()
