from dataclasses import dataclass
from rest_framework import serializers


@dataclass
class CreateBrandRequest:
    name: str = None
    user_id: int = None


@dataclass
class UpdateBrandRequest:
    brand_id: int = None
    name: str = None
    is_active: bool = None
    user_id: int = None


@dataclass
class DecideBrandRequestRequest:
    request_id: int = None
    decision: str = None
    note: str = ''
    user_id: int = None


@dataclass
class ArtistBrandRequestRequest:
    name: str = None
    user_id: int = None


class CreateBrandSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)

    def create(self, validated_data) -> CreateBrandRequest:
        return CreateBrandRequest(**validated_data)


class UpdateBrandSerializer(serializers.Serializer):
    brand_id = serializers.IntegerField()
    name = serializers.CharField(max_length=100, required=False)
    is_active = serializers.BooleanField(required=False)

    def create(self, validated_data) -> UpdateBrandRequest:
        return UpdateBrandRequest(**validated_data)


class DecideBrandRequestSerializer(serializers.Serializer):
    request_id = serializers.IntegerField()
    decision = serializers.ChoiceField(choices=['approved', 'rejected'])
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default='')

    def create(self, validated_data) -> DecideBrandRequestRequest:
        return DecideBrandRequestRequest(**validated_data)


class ArtistBrandRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)

    def create(self, validated_data) -> ArtistBrandRequestRequest:
        return ArtistBrandRequestRequest(**validated_data)
