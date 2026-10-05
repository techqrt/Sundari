import dataclasses


@dataclasses.dataclass
class CreateDocumentRequest:
    document_type: str = None
    id_type: str = None
    document_number: str = None
    user_id: int = None
    present_url: str = None
