import dataclasses


@dataclasses.dataclass
class DeleteDocumentRequest:
    document_id: int = None
    user_id: int = None
