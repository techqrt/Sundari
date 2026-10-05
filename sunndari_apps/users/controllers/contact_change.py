from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.users.contact_change_requests import RequestContactChangeSerializer, VerifyContactChangeSerializer
from sunndari_apps.users.views.contact_change import ContactChangeView


class ContactChangeController:

    @extend_schema(
        description=(
            'Start changing your email OR phone number (send exactly one). A 6-digit code is sent to the NEW '
            'contact, valid 10 minutes; one request per minute. Nothing changes until it is verified.'
        ),
        request=RequestContactChangeSerializer,
        responses=SwaggerPage.response(description='Code sent to the new contact'),
        tags=['Users - Profile'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=RequestContactChangeSerializer).validate
    def request_change(request: Request) -> Response:
        return ContactChangeView().request_extract(params=request.params)

    @extend_schema(
        description='Enter the code sent to the new contact to apply the change. The code is single-use; 5 wrong tries burn it.',
        request=VerifyContactChangeSerializer,
        responses=SwaggerPage.response(description='Contact updated'),
        tags=['Users - Profile'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=VerifyContactChangeSerializer).validate
    def verify_change(request: Request) -> Response:
        return ContactChangeView().verify_extract(params=request.params)
