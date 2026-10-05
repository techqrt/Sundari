from sunndari_apps.authentication.models import User
from sunndari.constants import Constants


def require_admin(user_id: int) -> None:
    """Raises (-> HTTP 400 like every other refusal in this API) unless the caller is an admin."""
    user = User.get(user_id=user_id)
    if not user or user['role'] != 'admin':
        raise ValueError(Constants.forbidden_resource)
