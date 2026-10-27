"""Prints Postman-ready access tokens for existing users, the same way a login would issue them.

    venv/bin/python manage.py shell < docs/manual-testing/mint_tokens.py

Edit WHO below. A user has ONE live token at a time, so minting one signs that user out of the app (fine on a dev DB).
Tokens last JWT_EXPIRY_DAYS; run it again if one stops working."""
from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import generate_jwt_token

WHO = {                      # label -> user_id (see the runbook for which users to use)
    'artistToken': 2,        # approved artist, has no FCM device
    'artist2Token': 4,       # second approved artist
    'customerToken': 1,      # customer
}

for label, user_id in WHO.items():
    user = User.objects.get(pk=user_id)
    token = generate_jwt_token(user)
    user.access_token = token
    user.save()
    print(f'{label} (user {user_id}, {user.role}, {user.name or "no name"}):\n{token}\n')
