from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.payments.models import Payment
from sunndari_apps.wallet.models.customer_wallet import CustomerWallet
from sunndari_apps.wallet.models.redemption_tier import RedemptionTier
from sunndari_apps.wallet.dataclasses.request.get.get_eligible_tiers import GetEligibleTiersRequest
from sunndari_apps.wallet.serializers.response.get_all.eligible_tiers import EligibleTiersResponseSerializer
from sunndari.constants import Constants


class EligibleTiersView:

    @Common(response_handler=EligibleTiersResponseSerializer).exception_handler
    def get_extract(self, params: GetEligibleTiersRequest):
        booking = Booking.get(booking_id=params.booking_id)
        if not booking or booking['customer_id'] != params.user_id:
            raise ValueError(Constants.booking_not_found)

        # Counts cash paid PLUS any coin-redeemed value already settled on a prior
        # successful payment for this booking — total_paid_for_booking() alone would
        # understate this whenever redemption was used.
        already_settled = Payment.total_settled_for_booking(booking_id=params.booking_id)
        remaining_due = booking['total_amount'] - already_settled
        amount = params.amount if params.amount is not None else remaining_due
        if amount <= 0 or amount > remaining_due:
            raise ValueError(Constants.invalid_payment_amount)

        wallet = CustomerWallet.get(customer_id=params.user_id)
        balance_coins = wallet['balance_coins'] if wallet else 0

        # Same two guards initiate_extract enforces before accepting a redemption_tier_id
        # — a tier is only "eligible" here if it would actually be accepted there.
        tiers = RedemptionTier.objects.filter(
            is_active=True, rupee_value__lte=amount, coin_cost__lte=balance_coins,
        ).order_by('rupee_value').values('tier_id', 'rupee_value', 'coin_cost')

        data = [
            {'tierId': t['tier_id'], 'rupeeValue': t['rupee_value'], 'coinCost': t['coin_cost']}
            for t in tiers
        ]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=Constants.data_get, data=data)
        )
