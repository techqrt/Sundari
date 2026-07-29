from rest_framework import serializers
from sunndari.config import Configurations
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from datetime import datetime, time
from django.utils import timezone


class GetAllSerializer(serializers.Serializer):
    values = serializers.CharField(max_length=200, required=False, default='')
    page_num = serializers.IntegerField(default=1)
    limit = serializers.IntegerField(default=Configurations.pagination_count)
    sort_by = serializers.CharField(max_length=100, required=False, default='')
    sort_order = serializers.ChoiceField(choices=['asc', 'desc'], required=False, default='asc')
    filter_key = serializers.CharField(max_length=100, required=False, default='')
    filter_value = serializers.CharField(max_length=100, required=False, default='')
    search_key = serializers.CharField(max_length=100, required=False, default='')
    from_date = serializers.DateField(input_formats=['%d-%m-%y'], required=False, default='')
    to_date = serializers.DateField(input_formats=['%d-%m-%y'], required=False, default='')
    artist_id = serializers.IntegerField(required=False)

    def create(self, validated_data) -> GetAll:
        from_date = validated_data.get('from_date', None)
        to_date = validated_data.get('to_date', None)
        if from_date:
            validated_data['from_date'] = timezone.make_aware(
                value=datetime.combine(date=from_date, time=time.min)
            )
        if to_date:
            validated_data['to_date'] = timezone.make_aware(
                value=datetime.combine(date=to_date, time=time.max)
            )
        return GetAll(**validated_data)
