from rest_framework import serializers


class ArtistProfileSerializer(serializers.Serializer):
    artistId = serializers.IntegerField()
    userId = serializers.IntegerField()
    bio = serializers.CharField(allow_null=True, allow_blank=True)
    yearsExperience = serializers.IntegerField()
    city = serializers.CharField(allow_null=True, allow_blank=True)
    serviceRadiusKm = serializers.IntegerField()
    avgRating = serializers.DecimalField(max_digits=3, decimal_places=2)
    totalReviews = serializers.IntegerField()
    commissionRate = serializers.DecimalField(max_digits=5, decimal_places=2)
    approvalStatusId = serializers.IntegerField(allow_null=True)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class ArtistProfileResponseSerializer(serializers.Serializer):
    data = ArtistProfileSerializer()
