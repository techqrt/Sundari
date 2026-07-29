from rest_framework import serializers
from sunndari_apps.notifications.serializers.response.get.get_notification import NotificationSerializer


class NotificationGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=NotificationSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class NotificationResponseGetAllSerializer(serializers.Serializer):
    data = NotificationGetAllSerializer()
