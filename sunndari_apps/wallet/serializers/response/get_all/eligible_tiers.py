from rest_framework import serializers


class EligibleTierSerializer(serializers.Serializer):
    tierId = serializers.IntegerField()
    rupeeValue = serializers.DecimalField(max_digits=10, decimal_places=2)
    coinCost = serializers.IntegerField()


class EligibleTiersResponseSerializer(serializers.Serializer):
    data = serializers.ListField(child=EligibleTierSerializer())
