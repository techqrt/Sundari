from rest_framework import serializers
from sunndari_apps.customers.serializers.response.get.get_review import ReviewSerializer


class ReviewGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=ReviewSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class ReviewResponseGetAllSerializer(serializers.Serializer):
    data = ReviewGetAllSerializer()
