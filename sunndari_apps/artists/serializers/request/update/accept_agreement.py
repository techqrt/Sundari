from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.accept_agreement import AcceptAgreementRequest


class AcceptAgreementSerializer(serializers.Serializer):

    def create(self, validated_data) -> AcceptAgreementRequest:
        return AcceptAgreementRequest(**validated_data)
