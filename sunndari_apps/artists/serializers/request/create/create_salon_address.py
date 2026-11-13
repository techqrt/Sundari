import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from rest_framework import serializers

from sunndari.constants import Constants
from sunndari_apps.artists.dataclasses.request.create.create_salon_address import CreateSalonAddressRequest


# Characters that read as nothing: zero-width space/non-joiner/joiner, word joiner, byte-order mark.
_INVISIBLE = {'\u200b', '\u200c', '\u200d', '\u2060', '\ufeff'}
# Text-direction overrides and isolates: they can make a label display as something it is not.
_DIRECTION = set('\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069')


class SalonTextField(serializers.CharField):
    """A single line of plain text a customer will read. Refuses line breaks and other control characters,
    text-direction overrides, and text that has nothing visible in it (only zero-width characters), none of which a
    person typing a salon name or address means. Emoji and every script are fine; a zero-width joiner inside an
    emoji sequence is allowed as long as something visible is there too."""

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if value:
            if any(unicodedata.category(ch) == 'Cc' or ch in _DIRECTION for ch in value) or all(
                ch.isspace() or ch in _INVISIBLE for ch in value
            ):
                raise serializers.ValidationError(Constants.salon_text_invalid)
        return value


class CreateSalonAddressSerializer(serializers.Serializer):
    name = SalonTextField(max_length=100)
    address_line_1 = SalonTextField(max_length=255)
    address_line_2 = SalonTextField(max_length=255, required=False, allow_blank=True, allow_null=True)
    city = SalonTextField(max_length=100)
    # Same length rule as users.CustomerAddress (free text), plus the plain-text rule above.
    pin_code = SalonTextField(max_length=10)
    # A map picker or geocoder often returns more than six decimals; those are rounded, not refused. The field's own
    # precision checks run before any rounding and would refuse exactly those values, so they are left off here: the
    # range is checked on the raw value by min/max, then the value is rounded to six places below. A value inside the
    # range can never round outside it, because 90 and 180 are themselves exact at six places.
    latitude = serializers.DecimalField(max_digits=None, decimal_places=None, min_value=-90, max_value=90)
    longitude = serializers.DecimalField(max_digits=None, decimal_places=None, min_value=-180, max_value=180)

    @staticmethod
    def _six_places(value: Decimal) -> Decimal:
        return value.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)

    def validate_latitude(self, value):
        return self._six_places(value)

    def validate_longitude(self, value):
        return self._six_places(value)

    def validate(self, data):
        # 0, 0 is the default of an unset map position (a point in the sea off Africa), never a real salon.
        if data['latitude'] == 0 and data['longitude'] == 0:
            raise serializers.ValidationError({'latitude': Constants.salon_coordinates_unset})
        return data

    def create(self, validated_data) -> CreateSalonAddressRequest:
        return CreateSalonAddressRequest(**validated_data)
