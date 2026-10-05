import json
import os
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.permissions import require_admin
from sunndari_apps.common.uploads import validate_image_or_pdf, SAFE_CONTENT_TYPES
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.authentication.models import User
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.help_center.models.ticket import SupportTicket, SupportTicketAttachment
from sunndari_apps.notifications.utils import NotificationService
from sunndari.constants import Constants

MAX_ATTACHMENTS = 5
MAX_OPEN_TICKETS = 10


def _ticket_dict(ticket: SupportTicket, with_user: bool = False) -> dict:
    data = {
        'ticketId': ticket.ticket_id,
        'issueType': ticket.issue_type,
        'subject': ticket.subject,
        'description': ticket.description,
        'bookingId': ticket.booking_id,
        'status': ticket.status,
        'resolutionNote': ticket.resolution_note,
        'attachments': [
            {'attachmentId': a.attachment_id, 'url': f'/help_center/tickets/attachment/?attachment_id={a.attachment_id}'}
            for a in ticket.attachments.all().order_by('attachment_id')
        ],
        'createdAt': ticket.created_at,
        'updatedAt': ticket.updated_at,
    }
    if with_user:
        data['userId'] = ticket.user_id
        data['userName'] = ticket.user.name
        data['userRole'] = ticket.user.role
    return data


def _paginated(rows: list, params: GetAll) -> Response:
    pages = Paginator(rows, per_page=params.limit)
    if pages.num_pages < params.page_num:
        raise ValueError('Page limit exceeded!')
    data = Utils.add_page_parameter(
        final_data=json.loads(json.dumps(list(pages.page(params.page_num)), default=str)),
        page_num=params.page_num, total_page=pages.num_pages, present_url=params.present_url,
        next_page_required=pages.num_pages != params.page_num,
    )
    return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message=Constants.data_get, data=data))


def _apply_filters(qs, params: GetAll):
    if params.filter_key == 'status' and params.filter_value:
        qs = qs.filter(status=params.filter_value)
    elif params.filter_key == 'bookingId' and params.filter_value.isdigit():
        qs = qs.filter(booking_id=int(params.filter_value))
    elif params.filter_key == 'issueType' and params.filter_value:
        qs = qs.filter(issue_type=params.filter_value)
    if params.search_key:
        qs = qs.filter(Q(subject__icontains=params.search_key) | Q(description__icontains=params.search_key))
    return qs


class TicketView:
    """Tickets for any logged-in customer or artist (their own only)."""

    @Common().exception_handler
    def create_extract(self, params, files: list):
        if len(files) > MAX_ATTACHMENTS:
            raise ValueError(Constants.ticket_too_many_attachments)
        for upload in files:
            validate_image_or_pdf(upload)
        with transaction.atomic():
            if SupportTicket.objects.filter(user_id=params.user_id, status__in=SupportTicket.OPEN_STATUSES).count() >= MAX_OPEN_TICKETS:
                raise ValueError(Constants.ticket_limit)
            booking = None
            if params.booking_id:
                booking = Booking.objects.filter(booking_id=params.booking_id).filter(
                    Q(customer_id=params.user_id) | Q(artist__user_id=params.user_id),
                ).first()
                if not booking:
                    raise ValueError(Constants.booking_not_found)
            ticket = SupportTicket.objects.create(
                user_id=params.user_id, booking=booking, issue_type=params.issue_type,
                subject=params.subject.strip(), description=params.description.strip(),
            )
            for upload in files:
                SupportTicketAttachment.objects.create(ticket=ticket, file=upload)
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Ticket created', data={'ticket_id': ticket.ticket_id}),
        )

    @Common().exception_handler
    def get_extract(self, params):
        ticket = SupportTicket.objects.filter(ticket_id=params.ticket_id, user_id=params.user_id).first()
        if not ticket:
            raise ValueError(Constants.data_no_match)
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(
            message=Constants.data_get, data=json.loads(json.dumps(_ticket_dict(ticket), default=str)),
        ))

    @Common().exception_handler
    def get_all_extract(self, params: GetAll):
        qs = _apply_filters(SupportTicket.objects.filter(user_id=params.user_id), params).prefetch_related('attachments')
        order = 'created_at' if params.sort_order == 'asc' and params.sort_by else '-created_at'
        return _paginated([_ticket_dict(t) for t in qs.order_by(order, '-ticket_id')], params)

    @Common().exception_handler
    def close_extract(self, params):
        with transaction.atomic():
            ticket = SupportTicket.objects.select_for_update().filter(ticket_id=params.ticket_id, user_id=params.user_id).first()
            if not ticket:
                raise ValueError(Constants.data_no_match)
            if ticket.status == 'closed':
                raise ValueError(Constants.ticket_already_closed)
            ticket.status = 'closed'
            ticket.save()
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message='Ticket closed'))

    def download_extract(self, params):
        """Streams an attachment to the ticket's owner or an admin; same refusal as any other
        unknown id otherwise. Not wrapped in the JSON exception handler: it returns a file."""
        def refuse():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=Utils.error_response_data(
                message='Value Error ' + Constants.data_no_match, error=[Constants.data_no_match]))
        attachment = SupportTicketAttachment.objects.select_related('ticket').filter(attachment_id=params.attachment_id).first()
        if not attachment:
            return refuse()
        user = User.get(user_id=params.user_id)
        if attachment.ticket.user_id != params.user_id and not (user and user['role'] == 'admin'):
            return refuse()
        try:
            handle = attachment.file.storage.open(attachment.file.name, 'rb')
        except (FileNotFoundError, ValueError):
            return refuse()
        extension = os.path.splitext(attachment.file.name)[1].lower()
        safe_type = SAFE_CONTENT_TYPES.get(extension)
        response = FileResponse(handle, content_type=safe_type or 'application/octet-stream')
        response['Content-Disposition'] = f'{"inline" if safe_type else "attachment"}; filename="attachment_{attachment.attachment_id}{extension}"'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "sandbox; default-src 'none'"
        response['Cache-Control'] = 'private, no-store'
        return response


class AdminTicketView:

    @Common().exception_handler
    def get_all_extract(self, params: GetAll):
        require_admin(params.user_id)
        qs = _apply_filters(SupportTicket.objects.select_related('user'), params).prefetch_related('attachments')
        return _paginated([_ticket_dict(t, with_user=True) for t in qs.order_by('created_at', 'ticket_id')], params)

    @Common().exception_handler
    def get_extract(self, params):
        require_admin(params.user_id)
        ticket = SupportTicket.objects.select_related('user').filter(ticket_id=params.ticket_id).first()
        if not ticket:
            raise ValueError(Constants.data_no_match)
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(
            message=Constants.data_get, data=json.loads(json.dumps(_ticket_dict(ticket, with_user=True), default=str)),
        ))

    @Common().exception_handler
    def update_status_extract(self, params):
        require_admin(params.user_id)
        with transaction.atomic():
            ticket = SupportTicket.objects.select_for_update().filter(ticket_id=params.ticket_id).first()
            if not ticket:
                raise ValueError(Constants.data_no_match)
            if ticket.status == 'closed':
                raise ValueError(Constants.ticket_already_closed)
            ticket.status = params.status
            if params.resolution_note:
                ticket.resolution_note = params.resolution_note
            ticket.save()
        NotificationService.notify(
            user_id=ticket.user_id, title=f'Support ticket {params.status.replace("_", " ")}',
            message=(params.resolution_note or ticket.subject)[:140], type='support_ticket_update',
            booking_id=ticket.booking_id,
        )
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message='Ticket updated'))
