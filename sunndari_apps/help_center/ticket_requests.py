from dataclasses import dataclass
from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes

ISSUE_TYPES = ['booking', 'payment', 'service_quality', 'account', 'technical', 'other']
TICKET_STATUSES = ['open', 'in_progress', 'resolved', 'closed']


@dataclass
class CreateTicketRequest:
    issue_type: str = None
    subject: str = None
    description: str = None
    booking_id: int = None
    user_id: int = None
    present_url: str = None


@dataclass
class TicketIdRequest:
    ticket_id: int = None
    user_id: int = None
    present_url: str = None


@dataclass
class AttachmentIdRequest:
    attachment_id: int = None
    user_id: int = None
    present_url: str = None


@dataclass
class UpdateTicketStatusRequest:
    ticket_id: int = None
    status: str = None
    resolution_note: str = ''
    user_id: int = None
    present_url: str = None


class CreateTicketSerializer(serializers.Serializer):
    """Multipart: these fields plus up to 5 image/PDF files in `attachments`."""
    issue_type = serializers.ChoiceField(choices=ISSUE_TYPES)
    subject = serializers.CharField(max_length=150)
    description = serializers.CharField(max_length=2000)
    booking_id = serializers.IntegerField(required=False)

    def create(self, validated_data) -> CreateTicketRequest:
        return CreateTicketRequest(**validated_data)


class TicketIdSerializer(serializers.Serializer):
    ticket_id = serializers.IntegerField()

    def create(self, validated_data) -> TicketIdRequest:
        return TicketIdRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(name='ticket_id', required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY)]


class AttachmentIdSerializer(serializers.Serializer):
    attachment_id = serializers.IntegerField()

    def create(self, validated_data) -> AttachmentIdRequest:
        return AttachmentIdRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(name='attachment_id', required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY)]


class UpdateTicketStatusSerializer(serializers.Serializer):
    ticket_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=TICKET_STATUSES)
    resolution_note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default='')

    def create(self, validated_data) -> UpdateTicketStatusRequest:
        return UpdateTicketStatusRequest(**validated_data)
