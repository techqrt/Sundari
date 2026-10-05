from rest_framework import serializers


class ServiceAreaSerializer(serializers.Serializer):
    areaId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    city = serializers.CharField()
    travelChargeType = serializers.ChoiceField(choices=['free', 'per_visit', 'per_km'])
    chargeAmount = serializers.DecimalField(max_digits=8, decimal_places=2)
    isActive = serializers.BooleanField()
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class ServiceAreaResponseGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=ServiceAreaSerializer())
