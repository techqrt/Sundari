from rest_framework import serializers


class PortfolioSerializer(serializers.Serializer):
    portfolioId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    fileUrl = serializers.CharField(allow_blank=True)
    mediaType = serializers.CharField()
    subCategoryId = serializers.IntegerField()
    caption = serializers.CharField(allow_null=True, allow_blank=True)
    approvalStatusId = serializers.IntegerField(allow_null=True)
    isActive = serializers.BooleanField()
    isWorkSample = serializers.BooleanField(required=False)
    sortOrder = serializers.IntegerField(required=False)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class PortfolioResponseSerializer(serializers.Serializer):
    data = PortfolioSerializer()
