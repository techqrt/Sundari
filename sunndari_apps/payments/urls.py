from django.urls import path
from sunndari_apps.payments.controllers.payment_type import PaymentTypeController
from sunndari_apps.payments.controllers.initiate_payment import InitiatePaymentController
from sunndari_apps.payments.controllers.initiate_group_payment import InitiateGroupPaymentController
from sunndari_apps.payments.controllers.verify_payment import VerifyPaymentController
from sunndari_apps.payments.controllers.webhook import RazorpayWebhookController
from sunndari_apps.payments.controllers.payment import PaymentController

# /verify/ is the customer app's fast path (signature check + live Razorpay API confirmation). The webhook
# is the gateway's own word and covers the app being killed after paying. It replaces an earlier stub that
# was AllowAny with no signature check (anyone holding a gateway_order_id could have POSTed a fake "paid"):
# this one accepts a request only if its HMAC signature matches RAZORPAY_WEBHOOK_SECRET, and refuses
# everything while that secret is unset.
urlpatterns = [
    path('payment_types/', PaymentTypeController.get_all_payment_types, name='customer_get_all_payment_types'),
    path('initiate/', InitiatePaymentController.initiate_payment, name='customer_initiate_payment'),
    path('initiate_group/', InitiateGroupPaymentController.initiate_group_payment, name='customer_initiate_group_payment'),
    path('verify/', VerifyPaymentController.verify_payment, name='customer_verify_payment'),
    path('webhook/razorpay/', RazorpayWebhookController.razorpay_webhook, name='razorpay_webhook'),
    path('get/', PaymentController.get_payment, name='customer_get_payment'),
    path('get_all/', PaymentController.get_all_payments, name='customer_get_all_payments'),
]
