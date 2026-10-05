from dataclasses import dataclass


@dataclass
class VerifyDocumentRequest:
    document_id: int
    decision: str
    reason: str = ''
    user_id: int = None
