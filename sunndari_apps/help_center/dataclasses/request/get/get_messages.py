from dataclasses import dataclass
from sunndari_apps.common.dataclasses.request.get_all import GetAll


@dataclass
class GetMessagesRequest(GetAll):
    conversation_id: int = None
