# Test runs must never reach the real SMS gateway, even when .env has SMS_GATEWAY_* set for
# local development. Tests that exercise the gateway patch these values and the HTTP transport.
from sunndari.config import Configurations

Configurations.sms_gateway_url = ''
