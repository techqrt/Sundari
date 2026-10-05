import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', '') or ''
    if key:
        return Fernet(key.encode())
    # No dedicated key configured: derive one from SECRET_KEY. Fine for local use, but then
    # rotating SECRET_KEY makes previously encrypted values unreadable — set
    # FIELD_ENCRYPTION_KEY (Fernet.generate_key()) in any real deployment.
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()))


def encrypt_text(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_text(token: str):
    """Returns None (never raises) for an empty or undecryptable value."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
