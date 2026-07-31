from rest_framework import serializers


class PortfolioSerializer(serializers.Serializer):
    portfolioId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    fileUrl = serializers.CharField(allow_blank=True)
    mediaType = serializers.CharField()
    subCategoryId = serializers.IntegerField()
    caption = serializers.CharField(allow_null=True)
    approvalStatusId = serializers.IntegerField(allow_null=True)
    isActive = serializers.BooleanField()
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class PortfolioResponseSerializer(serializers.Serializer):
    data = PortfolioSerializer()
