from rest_framework import serializers
from sunndari.constants import Constants
from sunndari_apps.artists.dataclasses.request.create.create_document import CreateDocumentRequest
from sunndari_apps.artists.kyc import ID_TYPES, validate_id_number


class CreateDocumentSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=['id_proof', 'address_proof', 'certification'])
    id_type = serializers.ChoiceField(choices=list(ID_TYPES), required=False)
    document_number = serializers.CharField(required=False, allow_blank=True, max_length=100)

    def validate(self, data):
        if data['document_type'] == 'id_proof':
            if not data.get('id_type'):
                raise serializers.ValidationError({'id_type': Constants.kyc_id_type_required})
            if not data.get('document_number'):
                raise serializers.ValidationError({'document_number': Constants.kyc_number_required})
            try:
                data['document_number'] = validate_id_number(data['id_type'], data['document_number'])
            except ValueError as error:
                raise serializers.ValidationError({'document_number': str(error)})
        elif data.get('id_type'):
            raise serializers.ValidationError({'id_type': Constants.kyc_id_type_not_allowed})
        return data

    def create(self, validated_data) -> CreateDocumentRequest:
        return CreateDocumentRequest(**validated_data)
