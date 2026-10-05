from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari.config import Configurations
from sunndari.constants import Constants
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.utils import Utils


class PagesController:

    @extend_schema(
        description='Terms, Privacy and Contact details for the apps. Public (no login). A value is null until configured.',
        responses=SwaggerPage.response(description='Static pages'),
        tags=['Core - Pages'],
    )
    @api_view(['GET'])
    @authentication_classes([])
    @permission_classes([AllowAny])
    def get_pages(request: Request) -> Response:
        data = {
            'termsUrl': Configurations.terms_url or None,
            'privacyUrl': Configurations.privacy_url or None,
            'contactEmail': Configurations.contact_email or None,
            'contactPhone': Configurations.contact_phone or None,
            'agreementVersion': Configurations.agreement_version,
        }
        return Response(data=Utils.success_response_data(message=Constants.data_get, data=data))
