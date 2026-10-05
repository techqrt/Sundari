from rest_framework import serializers


class DocumentSerializer(serializers.Serializer):
    documentId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    documentType = serializers.CharField()
    idType = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    documentNumber = serializers.CharField(allow_null=True, allow_blank=True)
    fileUrl = serializers.CharField(allow_blank=True)
    backFileUrl = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    verificationStatusId = serializers.IntegerField(allow_null=True)
    rejectionReason = serializers.CharField(allow_null=True, allow_blank=True)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class DocumentResponseSerializer(serializers.Serializer):
    data = DocumentSerializer()
