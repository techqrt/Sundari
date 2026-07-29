from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.add_block import AddBlockRequest


class AddBlockSerializer(serializers.Serializer):
    block_date = serializers.DateField(input_formats=['%Y-%m-%d', '%d-%m-%Y'])
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)

    def create(self, validated_data) -> AddBlockRequest:
        return AddBlockRequest(
            block_date=str(validated_data['block_date']),
            note=validated_data.get('note'),
        )
