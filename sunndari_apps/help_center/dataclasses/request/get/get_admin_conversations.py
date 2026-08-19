from dataclasses import dataclass
from sunndari_apps.common.dataclasses.request.get_all import GetAll


@dataclass
class AdminGetConversationsRequest(GetAll):
    status: str = ''
