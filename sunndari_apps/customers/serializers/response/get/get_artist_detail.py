from rest_framework import serializers
from sunndari_apps.artists.serializers.response.get.get_profile import ArtistProfileSerializer
from sunndari_apps.artists.serializers.response.get.get_package import PackageSerializer
from sunndari_apps.artists.serializers.response.get.get_portfolio import PortfolioSerializer
from sunndari_apps.artists.serializers.response.get.service_offering import ServiceOfferingSerializer
from sunndari_apps.artists.serializers.response.get.get_addon import AddOnSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_service_area import ServiceAreaSerializer


class ArtistDetailDataSerializer(serializers.Serializer):
    profile = ArtistProfileSerializer()
    packages = serializers.ListField(child=PackageSerializer())
    portfolio = serializers.ListField(child=PortfolioSerializer())
    services = serializers.ListField(child=ServiceOfferingSerializer())
    addOns = serializers.ListField(child=AddOnSerializer(), required=False)
    serviceAreas = serializers.ListField(child=ServiceAreaSerializer(), required=False)


class ArtistDetailResponseSerializer(serializers.Serializer):
    data = ArtistDetailDataSerializer()
