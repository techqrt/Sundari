from rest_framework import serializers
from sunndari_apps.artists.serializers.response.get.get_portfolio import PortfolioSerializer


class PortfolioGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=PortfolioSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class PortfolioResponseGetAllSerializer(serializers.Serializer):
    data = PortfolioGetAllSerializer()
