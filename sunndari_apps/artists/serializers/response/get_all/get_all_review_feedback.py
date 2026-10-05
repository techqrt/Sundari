from rest_framework import serializers


class ReviewFeedbackSerializer(serializers.Serializer):
    feedbackId = serializers.IntegerField()
    decision = serializers.ChoiceField(choices=['approved', 'rejected'])
    message = serializers.CharField(allow_blank=True)
    createdAt = serializers.DateTimeField()


class ReviewFeedbackGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=ReviewFeedbackSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class ReviewFeedbackResponseGetAllSerializer(serializers.Serializer):
    data = ReviewFeedbackGetAllSerializer()
