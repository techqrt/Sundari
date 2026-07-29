from rest_framework import serializers
from sunndari_apps.artists.serializers.response.get.get_profile import ArtistProfileSerializer
from sunndari_apps.artists.serializers.response.get.get_package import PackageSerializer
from sunndari_apps.artists.serializers.response.get.get_portfolio import PortfolioSerializer
from sunndari_apps.artists.serializers.response.get.service_offering import ServiceOfferingSerializer


class ArtistDetailDataSerializer(serializers.Serializer):
    profile = ArtistProfileSerializer()
    packages = serializers.ListField(child=PackageSerializer())
    portfolio = serializers.ListField(child=PortfolioSerializer())
    services = serializers.ListField(child=ServiceOfferingSerializer())


class ArtistDetailResponseSerializer(serializers.Serializer):
    data = ArtistDetailDataSerializer()
