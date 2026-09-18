from django.urls import path
from sunndari_apps.wallet.controllers.eligible_tiers import EligibleTiersController
from sunndari_apps.wallet.controllers.wallet import WalletController

urlpatterns = [
    path('eligible_tiers/', EligibleTiersController.get_eligible_tiers, name='customer_get_eligible_tiers'),
    path('get/', WalletController.get_wallet, name='customer_get_wallet'),
    path('transactions/', WalletController.get_all_transactions, name='customer_get_all_wallet_transactions'),
]
