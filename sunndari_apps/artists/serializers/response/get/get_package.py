from rest_framework import serializers


class InclusionSerializer(serializers.Serializer):
    inclusionId = serializers.IntegerField()
    inclusionText = serializers.CharField()
    order = serializers.IntegerField()


class PackageSerializer(serializers.Serializer):
    packageId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    subCategoryId = serializers.IntegerField()
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    durationMinutes = serializers.IntegerField()
    description = serializers.CharField(allow_null=True)
    isActive = serializers.BooleanField()
    inclusions = serializers.ListField(child=InclusionSerializer())
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class PackageResponseSerializer(serializers.Serializer):
    data = PackageSerializer()
