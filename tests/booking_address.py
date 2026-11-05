from sunndari_apps.authentication.models import User
from sunndari_apps.users.models.customer_address import CustomerAddress


def address_for(client) -> dict:
    """{'address_id': ...} for the customer behind `client`: a booking now always names an address, so a test that is
    not about addresses sends this one. Created once per customer, found again on the next call."""
    token = client._credentials['HTTP_AUTHORIZATION'].split()[1]
    user = User.objects.get(access_token=token)
    address = CustomerAddress.objects.filter(user=user).first() or CustomerAddress.objects.create(
        user=user, address_line_1='12 Test Street', city='Gurugram', pin_code='122001',
    )
    return {'address_id': address.address_id}
