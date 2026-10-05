from rest_framework import serializers
from sunndari_apps.admin_panel.dataclasses.request.update.verify_document import VerifyDocumentRequest


class VerifyDocumentSerializer(serializers.Serializer):
    document_id = serializers.IntegerField()
    decision = serializers.ChoiceField(choices=['approved', 'rejected'])
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')

    def validate(self, data):
        if data['decision'] == 'rejected' and not data.get('reason'):
            raise serializers.ValidationError({'reason': 'A reason is required when rejecting a document.'})
        return data

    def create(self, validated_data) -> VerifyDocumentRequest:
        return VerifyDocumentRequest(**validated_data)
