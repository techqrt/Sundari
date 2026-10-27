from sunndari_apps.authentication.models import User
from sunndari.constants import Constants


def is_admin(user_id: int) -> bool:
    """True when the caller is an admin (used to decide what a listing shows; require_admin refuses instead)."""
    user = User.get(user_id=user_id)
    return bool(user) and user['role'] == 'admin'


def is_artist(user_id: int) -> bool:
    """True when the caller is an artist (used to decide what a listing shows; require_artist refuses instead)."""
    user = User.get(user_id=user_id)
    return bool(user) and user['role'] == 'artist'


def require_admin(user_id: int) -> None:
    """Raises (-> HTTP 400 like every other refusal in this API) unless the caller is an admin."""
    user = User.get(user_id=user_id)
    if not user or user['role'] != 'admin':
        raise ValueError(Constants.forbidden_resource)


def require_artist(user_id: int) -> None:
    """Raises (-> HTTP 400 like every other refusal in this API) unless the caller is an artist."""
    user = User.get(user_id=user_id)
    if not user or user['role'] != 'artist':
        raise ValueError(Constants.forbidden_resource)
