from rest_framework import serializers


class ReviewSerializer(serializers.Serializer):
    reviewId = serializers.IntegerField()
    bookingId = serializers.IntegerField()
    customerId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    rating = serializers.IntegerField()
    comment = serializers.CharField(allow_null=True, allow_blank=True)
    reply = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    repliedAt = serializers.DateTimeField(allow_null=True, required=False)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class ReviewResponseSerializer(serializers.Serializer):
    data = ReviewSerializer()
