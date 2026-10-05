from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.reply_review import ReplyReviewRequest


class ReplyReviewSerializer(serializers.Serializer):
    review_id = serializers.IntegerField()
    reply = serializers.CharField(min_length=1, max_length=1000)

    def create(self, validated_data) -> ReplyReviewRequest:
        return ReplyReviewRequest(**validated_data)
