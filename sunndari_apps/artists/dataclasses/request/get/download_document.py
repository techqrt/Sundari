import dataclasses


@dataclasses.dataclass
class DownloadDocumentRequest:
    document_id: int = None
    side: str = 'front'
    user_id: int = None
    present_url: str = None
