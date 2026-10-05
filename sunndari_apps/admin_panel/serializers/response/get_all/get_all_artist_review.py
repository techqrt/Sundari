from rest_framework import serializers


class ArtistReviewQueueItemSerializer(serializers.Serializer):
    artistId = serializers.IntegerField()
    userId = serializers.IntegerField()
    bio = serializers.CharField(allow_null=True, allow_blank=True)
    yearsExperience = serializers.IntegerField()
    city = serializers.CharField(allow_null=True, allow_blank=True)
    serviceRadiusKm = serializers.IntegerField()
    approvalStatusId = serializers.IntegerField(allow_null=True)
    submittedForReviewAt = serializers.DateTimeField(allow_null=True)
    createdAt = serializers.DateTimeField()


class ArtistReviewQueueGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=ArtistReviewQueueItemSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class ArtistReviewQueueResponseGetAllSerializer(serializers.Serializer):
    data = ArtistReviewQueueGetAllSerializer()
