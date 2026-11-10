from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.utils import timezone

from sunndari.config import Configurations
from sunndari.constants import Constants
from sunndari_apps.artists.models.promo_code import PromoCode, PromoRedemption
from sunndari_apps.artists.models.registration_payment import ArtistRegistrationPayment

CENT = Decimal('0.01')
# The smallest amount Razorpay will create an order for (₹1). A discount that would leave less than this,
# but more than nothing, cannot be charged and is refused.
GATEWAY_MINIMUM = Decimal('1.00')


class RegistrationFee:
    """The single place the artist registration fee, a promo discount and the payable amount are worked out.
    Everything is calculated on the server from the configured fee and the stored promo code; no amount or
    percentage from a client is ever read."""

    @staticmethod
    def fee() -> Decimal:
        return Decimal(Configurations.artist_registration_fee).quantize(CENT, rounding=ROUND_HALF_UP)

    @staticmethod
    def calculate(discount_percent=0) -> dict:
        """discount = fee x percent / 100 and payable = fee - discount, each rounded half-up to 2 places."""
        fee = RegistrationFee.fee()
        percent = Decimal(discount_percent or 0)
        discount = (fee * percent / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
        return {'fee': fee, 'discount_percent': percent, 'discount': discount, 'payable': fee - discount}

    @staticmethod
    def is_paid(artist_id: int) -> bool:
        """A completed registration payment that has not been voided or refunded."""
        return ArtistRegistrationPayment.objects.filter(
            artist_id=artist_id, paid_at__isnull=False, refund_requested_at__isnull=True,
        ).exists()

    @staticmethod
    def find_promo(code: str, artist_id: int) -> PromoCode:
        """The promo code if this artist may use it now; otherwise a ValueError saying why. The checks are
        advisory here (nothing is recorded); the redemption itself is made under a lock when payment starts."""
        promo = PromoCode.objects.filter(code=(code or '').strip().upper(), is_active=True).first()
        if promo is None:
            raise ValueError(Constants.promo_invalid)
        now = timezone.now()
        if (promo.valid_from and promo.valid_from > now) or (promo.valid_until and promo.valid_until < now):
            raise ValueError(Constants.promo_expired)
        live = PromoRedemption.objects.filter(promo=promo, status__in=['reserved', 'redeemed'])
        if live.filter(artist_id=artist_id).exists():
            raise ValueError(Constants.promo_already_used)
        if promo.max_redemptions is not None and live.count() >= promo.max_redemptions:
            raise ValueError(Constants.promo_fully_redeemed)
        return promo

    @staticmethod
    def quote(artist_id: int, promo_code: str = None) -> dict:
        """What this artist would pay now, with the promo code applied if one is given."""
        promo = RegistrationFee.find_promo(promo_code, artist_id) if promo_code else None
        amounts = RegistrationFee.calculate(promo.discount_percent if promo else 0)
        if 0 < amounts['payable'] < GATEWAY_MINIMUM:
            raise ValueError(Constants.promo_not_applicable)
        return {**amounts, 'promo': promo}
