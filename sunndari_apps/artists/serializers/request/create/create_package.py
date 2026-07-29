from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.create_package import CreatePackageRequest


class CreatePackageSerializer(serializers.Serializer):
    sub_category_id = serializers.IntegerField()
    name = serializers.CharField(max_length=200)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=500)
    duration_minutes = serializers.IntegerField(min_value=1)
    description = serializers.CharField(required=False, allow_blank=True)
    inclusions = serializers.ListField(child=serializers.CharField(max_length=300), required=False, default=list)

    def create(self, validated_data) -> CreatePackageRequest:
        return CreatePackageRequest(**validated_data)
