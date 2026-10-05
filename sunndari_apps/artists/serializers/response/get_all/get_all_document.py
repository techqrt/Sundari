from rest_framework import serializers
from sunndari_apps.artists.serializers.response.get.get_document import DocumentSerializer


class DocumentGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=DocumentSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class DocumentResponseGetAllSerializer(serializers.Serializer):
    data = DocumentGetAllSerializer()
