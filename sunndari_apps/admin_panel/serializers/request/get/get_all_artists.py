from dataclasses import fields

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import serializers

from sunndari_apps.admin_panel.dataclasses.request.get.get_all_artists import GetAllArtistsRequest
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.common.swagger import SwaggerPage


class GetAllArtistsSerializer(GetAllSerializer):
    approval_status = serializers.ChoiceField(
        choices=['pending', 'approved', 'rejected', 'suspended'], required=False,
    )
    # paid: a completed, un-refunded payment. exempt: waived (e.g. approved before the fee existed).
    # unpaid: neither, i.e. not yet eligible to switch bookings on.
    registration = serializers.ChoiceField(choices=['paid', 'unpaid', 'exempt'], required=False)
    accepting = serializers.BooleanField(required=False)

    FILTERS = ('approval_status', 'registration', 'accepting')

    def create(self, validated_data) -> GetAllArtistsRequest:
        extras = {name: validated_data.pop(name, None) for name in self.FILTERS}
        base = super().create(validated_data)
        return GetAllArtistsRequest(**{f.name: getattr(base, f.name) for f in fields(GetAll)}, **extras)

    @staticmethod
    def get_parameters():
        return [
            parameter for parameter in SwaggerPage.get_all_parameters()
            if parameter.name not in ('filter_key', 'filter_value', 'from_date', 'to_date', 'values')
        ] + [
            OpenApiParameter(name='approval_status', description='pending, approved, rejected or suspended',
                             required=False, location=OpenApiParameter.QUERY, type=str,
                             enum=['pending', 'approved', 'rejected', 'suspended']),
            OpenApiParameter(name='registration', description='paid, unpaid (not yet eligible) or exempt',
                             required=False, location=OpenApiParameter.QUERY, type=str,
                             enum=['paid', 'unpaid', 'exempt']),
            OpenApiParameter(name='accepting', description='true or false: bookings switched on or off',
                             required=False, location=OpenApiParameter.QUERY, type=OpenApiTypes.BOOL),
        ]
