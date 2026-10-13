from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.add_block import AddBlockRequest


class AddBlockSerializer(serializers.Serializer):
    block_date = serializers.DateField(input_formats=['%Y-%m-%d', '%d-%m-%Y'])
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)

    def validate(self, data):
        start, end = data.get('start_time'), data.get('end_time')
        if (start is None) != (end is None):
            raise serializers.ValidationError('start_time and end_time must be sent together.')
        if start is not None and end <= start:
            raise serializers.ValidationError({'end_time': 'end_time must be after start_time.'})
        return data

    def create(self, validated_data) -> AddBlockRequest:
        start, end = validated_data.get('start_time'), validated_data.get('end_time')
        return AddBlockRequest(
            block_date=str(validated_data['block_date']),
            start_time=str(start) if start is not None else None,
            end_time=str(end) if end is not None else None,
            note=validated_data.get('note'),
        )
