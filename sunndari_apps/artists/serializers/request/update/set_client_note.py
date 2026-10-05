from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.set_client_note import SetClientNoteRequest


class SetClientNoteSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    note = serializers.CharField(max_length=1000, allow_blank=True)

    def create(self, validated_data) -> SetClientNoteRequest:
        return SetClientNoteRequest(**validated_data)
