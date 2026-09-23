from django.urls import path
from sunndari_apps.payments.controllers.payment_type import PaymentTypeController
from sunndari_apps.payments.controllers.initiate_payment import InitiatePaymentController
from sunndari_apps.payments.controllers.initiate_group_payment import InitiateGroupPaymentController
from sunndari_apps.payments.controllers.verify_payment import VerifyPaymentController
from sunndari_apps.payments.controllers.payment import PaymentController

# No webhook route: this integration verifies payments via client-driven /verify/ (signature
# check + live Razorpay API confirmation) rather than an inbound webhook — see plan discussion.
# The old webhook stub was removed entirely rather than left dormant: it was AllowAny with no
# signature verification, which would have been a live exploit once booking confirmation
# started depending on Payment.status (anyone who obtained a gateway_order_id could have
# POSTed a fake {"status": "paid"} there).
urlpatterns = [
    path('payment_types/', PaymentTypeController.get_all_payment_types, name='customer_get_all_payment_types'),
    path('initiate/', InitiatePaymentController.initiate_payment, name='customer_initiate_payment'),
    path('initiate_group/', InitiateGroupPaymentController.initiate_group_payment, name='customer_initiate_group_payment'),
    path('verify/', VerifyPaymentController.verify_payment, name='customer_verify_payment'),
    path('get/', PaymentController.get_payment, name='customer_get_payment'),
    path('get_all/', PaymentController.get_all_payments, name='customer_get_all_payments'),
]
