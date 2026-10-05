from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.help_center.ticket_requests import (
    CreateTicketSerializer, TicketIdSerializer, AttachmentIdSerializer, UpdateTicketStatusSerializer,
)
from sunndari_apps.help_center.views.ticket import TicketView, AdminTicketView


class TicketController:

    @extend_schema(
        description=(
            'Raise a support ticket (customers and artists). Multipart: issue_type, subject, description, '
            'optional booking_id (must be one of your own bookings) and up to 5 image/PDF files in `attachments`.'
        ),
        request={'multipart/form-data': CreateTicketSerializer},
        responses=SwaggerPage.response(description='Ticket created'), tags=['Help center - Tickets'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CreateTicketSerializer).validate
    def create_ticket(request: Request) -> Response:
        return TicketView().create_extract(params=request.params, files=request.FILES.getlist('attachments'))

    @extend_schema(description='One of your tickets.', parameters=TicketIdSerializer.get_parameters(),
                   responses=SwaggerPage.response(description='Ticket'), tags=['Help center - Tickets'])
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=TicketIdSerializer).validate
    def get_ticket(request: Request) -> Response:
        return TicketView().get_extract(params=request.params)

    @extend_schema(
        description='Your tickets, newest first. Narrow with filter_key=status|bookingId|issueType.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(description='Tickets'), tags=['Help center - Tickets'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_tickets(request: Request) -> Response:
        return TicketView().get_all_extract(params=request.params)

    @extend_schema(description='Close one of your own tickets.', request=TicketIdSerializer,
                   responses=SwaggerPage.response(description='Ticket closed'), tags=['Help center - Tickets'])
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=TicketIdSerializer).validate
    def close_ticket(request: Request) -> Response:
        return TicketView().close_extract(params=request.params)

    @extend_schema(description='Download a ticket attachment (ticket owner or admin).',
                   parameters=AttachmentIdSerializer.get_parameters(),
                   responses={(200, 'application/octet-stream'): bytes}, tags=['Help center - Tickets'])
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=AttachmentIdSerializer).validate
    def download_attachment(request: Request) -> Response:
        return TicketView().download_extract(params=request.params)

    @extend_schema(description='All tickets, oldest first. Narrow with filter_key=status|bookingId|issueType. Admin only.',
                   parameters=SwaggerPage.get_all_parameters(),
                   responses=SwaggerPage.response(description='Tickets'), tags=['Help center - Admin tickets'])
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def admin_get_all_tickets(request: Request) -> Response:
        return AdminTicketView().get_all_extract(params=request.params)

    @extend_schema(description='Any ticket, with the user. Admin only.', parameters=TicketIdSerializer.get_parameters(),
                   responses=SwaggerPage.response(description='Ticket'), tags=['Help center - Admin tickets'])
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=TicketIdSerializer).validate
    def admin_get_ticket(request: Request) -> Response:
        return AdminTicketView().get_extract(params=request.params)

    @extend_schema(description='Change a ticket status (open, in_progress, resolved, closed) with an optional resolution note; notifies the user. Admin only.',
                   request=UpdateTicketStatusSerializer,
                   responses=SwaggerPage.response(description='Ticket updated'), tags=['Help center - Admin tickets'])
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=UpdateTicketStatusSerializer).validate
    def admin_update_ticket_status(request: Request) -> Response:
        return AdminTicketView().update_status_extract(params=request.params)
