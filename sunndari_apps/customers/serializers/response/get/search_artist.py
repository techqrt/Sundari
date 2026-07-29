from rest_framework import serializers


class ArtistSearchResultSerializer(serializers.Serializer):
    artistId = serializers.IntegerField()
    name = serializers.CharField(allow_null=True)
    bio = serializers.CharField(allow_null=True)
    city = serializers.CharField(allow_null=True)
    yearsExperience = serializers.IntegerField()
    avgRating = serializers.DecimalField(max_digits=3, decimal_places=2)
    totalReviews = serializers.IntegerField()
    startingPrice = serializers.DecimalField(max_digits=10, decimal_places=2)
