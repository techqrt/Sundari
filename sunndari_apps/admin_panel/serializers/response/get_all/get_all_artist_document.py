from rest_framework import serializers


class AdminArtistDocumentSerializer(serializers.Serializer):
    documentId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    documentType = serializers.CharField()
    idType = serializers.CharField(allow_null=True)
    documentNumber = serializers.CharField(allow_null=True, allow_blank=True)
    idNumber = serializers.CharField(allow_null=True, allow_blank=True)
    fileUrl = serializers.CharField()
    backFileUrl = serializers.CharField(allow_null=True)
    verificationStatus = serializers.CharField(allow_null=True)
    rejectionReason = serializers.CharField(allow_null=True, allow_blank=True)
    createdAt = serializers.DateTimeField()


class AdminArtistDocumentResponseSerializer(serializers.Serializer):
    data = serializers.ListField(child=AdminArtistDocumentSerializer())
