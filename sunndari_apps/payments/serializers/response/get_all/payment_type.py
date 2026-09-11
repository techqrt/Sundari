from rest_framework import serializers


class PaymentTypeItemSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class PaymentTypeListResponseSerializer(serializers.Serializer):
    data = serializers.ListField(child=PaymentTypeItemSerializer())
