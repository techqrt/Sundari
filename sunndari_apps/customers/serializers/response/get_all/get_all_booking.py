from rest_framework import serializers
from sunndari_apps.customers.serializers.response.get.get_booking import BookingSerializer


class BookingGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=BookingSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class BookingResponseGetAllSerializer(serializers.Serializer):
    data = BookingGetAllSerializer()
