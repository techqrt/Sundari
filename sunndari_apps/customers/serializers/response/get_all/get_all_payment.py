from rest_framework import serializers
from sunndari_apps.customers.serializers.response.get.get_payment import PaymentSerializer


class PaymentGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=PaymentSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class PaymentResponseGetAllSerializer(serializers.Serializer):
    data = PaymentGetAllSerializer()
