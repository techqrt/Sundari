from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.update_package import UpdatePackageRequest


class UpdatePackageSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    sub_category_id = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=200, required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=500, required=False)
    duration_minutes = serializers.IntegerField(min_value=1, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    inclusions = serializers.ListField(child=serializers.CharField(max_length=300), required=False)

    def create(self, validated_data) -> UpdatePackageRequest:
        return UpdatePackageRequest(**validated_data)
