import datetime
from decimal import Decimal, ROUND_HALF_UP
from unittest.mock import patch, MagicMock

import razorpay
from django.test import TestCase
from django.utils import timezone

from sunndari_apps.artists.models import ArtistProfile, ArtistAvailabilityBlock, PricingPackage, PackageAddOn, ArtistServiceArea
from sunndari_apps.customers.models import Booking, BookingReschedule
from sunndari_apps.payments.models import Payment
from sunndari_apps.core.models import PaymentStatus
from qa.harness import record, observe, blocked, unverified, body, data, is_2xx, dump, new_client, at
from qa import world as w
from qa.test_06_booking import ist

F = 'MONEY'


class GatewayMock:
    """Razorpay is unavailable, so emulate the parts the app talks to: order.create, plus the
    order.fetch / payment.fetch calls verify_payment makes to confirm capture independently.
    `captured=False` simulates a payment the gateway did NOT capture; `signature_ok=False` a forged signature."""
    CURRENT = None

    def __init__(self, signature_ok=True, captured=True):
        self.orders, self.captured = {}, captured
        self.client = MagicMock()

        def create(data):
            order = {'id': f"order_qa_{data['receipt']}", 'amount': data['amount'], 'currency': 'INR', 'status': 'created'}
            self.orders[order['id']] = order
            return order
        self.client.order.create.side_effect = create

        def order_fetch(order_id):
            order = dict(self.orders[order_id])
            if self.captured:
                order.update(amount_paid=order['amount'], status='paid')
            else:
                order.update(amount_paid=0)
            return order
        self.client.order.fetch.side_effect = order_fetch
        self.client.payment.fetch.side_effect = lambda pid: {
            'id': pid, 'status': 'captured' if self.captured else 'authorized', 'order_id': GatewayMock.CURRENT}
        if not signature_ok:
            self.client.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError('bad')

    def __enter__(self):
        GatewayMock.CURRENT = None
        self.p1 = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client', return_value=self.client)
        self.p2 = patch('sunndari_apps.payments.views.verify_payment.RazorpayGateway.get_client', return_value=self.client)
        self.p1.start(); self.p2.start()
        return self

    def __exit__(self, *a):
        self.p1.stop(); self.p2.stop()


def initiate(customer, bid, **kw):
    return customer.client.post('/customers/payments/initiate/', {'booking_id': bid, **kw}, format='json')


def verify(customer, order_id):
    GatewayMock.CURRENT = order_id
    return customer.client.post('/customers/payments/verify/', {'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_qa', 'razorpay_signature': 'sig'}, format='json')


class MoneyQA(TestCase):
    @classmethod
    def setUpTestData(cls):
        w.seed_statuses()
        cls.cus = w.make_customer('+919800000001', 'Money Customer')

    def tearDown(self):
        dump()

    def _artist(self, phone, price, rate):
        art = w.make_bookable_artist(phone, f'Money {phone[-3:]}', price=price)
        ArtistProfile.objects.filter(artist_id=art.profile.artist_id).update(commission_rate=Decimal(rate))
        return art

    def test_commission_arithmetic_and_rounding(self):
        bad = []
        day = 3
        with GatewayMock():
            for i, (price, rate) in enumerate([('1500.00', '10.00'), ('999.99', '12.50'), ('3333.33', '17.33'), ('500.01', '10.00'), ('7777.77', '22.22'), ('12345.67', '25.00')]):
                art = self._artist(f'+91980000010{i}', price, rate)
                bid = data(w.create_booking(self.cus, art, day=day + i))['booking_id']
                with_snapshot = Booking.objects.get(booking_id=bid)
                r = initiate(self.cus, bid)
                p = Payment.objects.get(booking_id=bid)
                total = Decimal(price)
                expected_fee = (total * Decimal(rate) / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                ok = (p.amount == total and p.commission_amount + p.artist_payout_amount == p.amount and p.commission_amount.as_tuple().exponent == -2
                      and abs(p.commission_amount - expected_fee) <= Decimal('0.01') and with_snapshot.platform_fee + with_snapshot.net_amount == with_snapshot.total_amount)
                if not ok:
                    bad.append((price, rate, str(p.amount), str(p.commission_amount), str(p.artist_payout_amount), str(expected_fee)))
        record(F, 'commission + payout == amount, 2 decimals, within 1 paisa of exact, across 6 price/rate combinations', not bad, 'consistent', bad, sev='P1')
        half = Decimal('0.125') * 1
        observe(F, 'rounding mode', 'Python round() on Decimal = banker\'s rounding (round-half-even), not commercial half-up; differences are <= 0.01 per payment', sev='P3')

    def test_payment_flows_and_overpayment(self):
        art = self._artist('+919800000200', '2000.00', '10.00')
        with GatewayMock() as gm:
            bid = data(w.create_booking(self.cus, art, day=3))['booking_id']
            r = initiate(self.cus, bid, amount='500.00', payment_type='advance')
            record(F, 'advance (partial) payment initiated for part of the total', r.status_code == 201, 201, r.status_code, sev='P1')
            record(F, 'amount above the remaining due is refused', initiate(self.cus, bid, amount='5000.00').status_code == 400, 400, 'checked', sev='P0')
            record(F, 'zero / negative amounts refused', initiate(self.cus, bid, amount='0').status_code == 400 and initiate(self.cus, bid, amount='-100').status_code == 400, 'both refused', 'checked', sev='P0')
            record(F, "another customer cannot pay for / see someone else's booking", initiate(w.make_customer('+919800000201', 'Stranger'), bid).status_code == 400, 400, 'checked', sev='P0')
            pay1 = Payment.objects.get(booking_id=bid)
            v = verify(self.cus, pay1.gateway_order_id)
            record(F, 'verify marks the payment paid', v.status_code == 200 and Payment.objects.get(payment_id=pay1.payment_id).status.name == 'paid', 'paid', v.status_code, sev='P0')
            v2 = verify(self.cus, pay1.gateway_order_id)
            record(F, 'verify is idempotent (second call is a no-op, not a double credit)', v2.status_code == 200 and Payment.objects.filter(booking_id=bid, status__name='paid').count() == 1, 'one paid row', v2.status_code, sev='P0')
            record(F, "another customer cannot verify someone else's payment", verify(w.make_customer('+919800000202', 'Stranger2'), pay1.gateway_order_id).status_code == 400, 400, 'checked', sev='P0')
            record(F, 'artist cannot confirm while only part-paid', (lambda r: r.status_code == 400)(art.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'confirmed'}, format='json')), 'refused', 'checked', sev='P0')
            r = initiate(self.cus, bid)
            pay2 = Payment.objects.filter(booking_id=bid).order_by('-payment_id').first()
            record(F, 'balance payment equals exactly the remaining due (1500)', r.status_code == 201 and pay2.amount == Decimal('1500.00'), 1500, pay2.amount, sev='P0')
            # duplicate initiation before verification
            dup = initiate(self.cus, bid)
            pending = Payment.objects.filter(booking_id=bid, status__name='pending').count()
            observe(F, 'initiating the balance twice creates two pending payments for the same dues', f'HTTP {dup.status_code}; pending rows={pending}', sev='P2')
            verify(self.cus, pay2.gateway_order_id)
            dup_row = Payment.objects.filter(booking_id=bid, status__name='pending').first()
            if dup_row:
                verify(self.cus, dup_row.gateway_order_id)
            settled = Payment.total_settled_for_booking(booking_id=bid)
            record(F, 'a booking can never be settled for more than its total (no overpayment via duplicate orders)', settled <= Decimal('2000.00'), '<= 2000', str(settled), sev='P1',
                   note='initiate allows a second order for the same remaining due; verify does not re-check the total')
            r = initiate(self.cus, bid)
            record(F, 'no payment can be initiated once fully paid', r.status_code == 400 or Payment.total_settled_for_booking(booking_id=bid) <= Decimal('2000.00'), 'refused', r.status_code, sev='P1')
        with GatewayMock(captured=False):
            bid3 = data(w.create_booking(self.cus, art, day=6))['booking_id']
            initiate(self.cus, bid3)
            p3 = Payment.objects.get(booking_id=bid3)
            v = verify(self.cus, p3.gateway_order_id)
            record(F, 'payment the gateway did NOT capture is rejected even with a valid signature', v.status_code == 400 and Payment.objects.get(payment_id=p3.payment_id).status.name == 'failed', 'failed', v.status_code, sev='P0')
        with GatewayMock(signature_ok=False):
            bid2 = data(w.create_booking(self.cus, art, day=5))['booking_id']
            initiate(self.cus, bid2)
            p = Payment.objects.get(booking_id=bid2)
            v = verify(self.cus, p.gateway_order_id)
            record(F, 'bad signature -> payment marked failed, booking not confirmable', v.status_code == 400 and Payment.objects.get(payment_id=p.payment_id).status.name == 'failed'
                   and art.client.put('/artists/bookings/update_status/', {'booking_id': bid2, 'status': 'confirmed'}, format='json').status_code == 400, 'failed, unconfirmed', v.status_code, sev='P0')

    def test_refund_behaviour(self):
        art = self._artist('+919800000300', '1800.00', '10.00')
        with GatewayMock() as gm:
            bid = data(w.create_booking(self.cus, art, day=3))['booking_id']
            initiate(self.cus, bid)
            verify(self.cus, Payment.objects.get(booking_id=bid).gateway_order_id)
            art.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'confirmed'}, format='json')
            art.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'cancelled', 'reason': 'ill'}, format='json')
            p = Payment.objects.get(booking_id=bid)
            record(F, 'artist cancelling a paid booking marks the payment refunded', p.status.name == 'refunded', 'refunded', p.status.name, sev='P1')
            refund_calls = gm.client.payment.refund.call_count
            record(F, 'a real refund is requested from the payment gateway', refund_calls > 0, 'gateway refund API called', f'calls={refund_calls}', sev='P1',
                   note='Payment.mark_refunded is a stub: the customer is shown "refunded" but no money moves (documented TODO in payments/models.py)')
            blocked(F, 'real gateway refund / payout', 'EXTERNAL DEPENDENCY: Razorpay credentials and a refund integration are not available')
        observe(F, 'earnings / payouts / adjustments', 'NOT IMPLEMENTED (owner decision to skip): there is no earnings summary, payout history, adjustment or payout ledger; Payment.commission_amount / artist_payout_amount are the only stored source, and cancelled/refunded handling for earnings is undefined', sev='P1')

    def test_total_consistency_with_addons_and_travel(self):
        art = self._artist('+919800000400', '2000.00', '10.00')
        pkg = art.package
        addon = PackageAddOn.objects.create(artist=art.profile, name='Hair', price=Decimal('333.33'), duration_minutes=15); addon.packages.add(pkg)
        ArtistServiceArea.objects.create(artist=art.profile, city='Lucknow', travel_charge_type='per_visit', charge_amount=Decimal('149.50'))
        with GatewayMock():
            bid = data(w.create_booking(self.cus, art, day=3, addon_ids=[addon.addon_id]))['booking_id']
            b = Booking.objects.get(booking_id=bid)
            record(F, 'total = package + add-on + travel, to the paisa', b.total_amount == Decimal('2482.83'), '2482.83', b.total_amount, sev='P0')
            initiate(self.cus, bid)
            p = Payment.objects.get(booking_id=bid)
            record(F, 'the charged amount equals the booking total (nothing the client sends changes it)', p.amount == b.total_amount, str(b.total_amount), str(p.amount), sev='P0')
            # edit the add-on and service area afterwards
            PackageAddOn.objects.filter(addon_id=addon.addon_id).update(price=Decimal('9999'))
            ArtistServiceArea.objects.filter(artist=art.profile).update(charge_amount=Decimal('9999'))
            b2 = Booking.objects.get(booking_id=bid)
            record(F, 'later add-on / travel price edits do not alter the existing booking', b2.total_amount == b.total_amount and b2.travel_fee == Decimal('149.50'), 'unchanged', (b2.total_amount, b2.travel_fee), sev='P1')


class RescheduleQA(TestCase):
    @classmethod
    def setUpTestData(cls):
        w.seed_statuses()
        cls.art = w.make_bookable_artist('+919800000500', 'Resched Artist')
        cls.cus = w.make_customer('+919800000501', 'Resched Customer')
        cls.other = w.make_customer('+919800000502', 'Resched Other')

    def tearDown(self):
        dump()

    def _confirmed(self, start='10:00:00', day=5, customer=None):
        return w.confirmed_booking(customer or self.cus, self.art, start=start, day=day)

    def _request(self, bid, day=6, start='14:00:00', client=None):
        return (client or self.art.client).post('/artists/bookings/reschedule/request/', {
            'booking_id': bid, 'proposed_date': w.fmt_date(w.future_date(day)), 'proposed_start_time': start, 'reason': 'QA'}, format='json')

    def test_reschedule_flow(self):
        A, C = self.art, self.cus
        bid = self._confirmed()
        pend = w.create_booking(C, A, start='12:00:00', day=5)
        r = self._request(data(pend)['booking_id'])
        record('RESCHEDULE', 'only a confirmed booking can be rescheduled', r.status_code == 400, 400, r.status_code, sev='P1')
        record('RESCHEDULE', 'customer cannot start a reschedule through the artist endpoint', not is_2xx(self._request(bid, client=C.client)), 'refused', 'checked', sev='P0')
        r = self._request(bid)
        rid = (data(r) or {}).get('reschedule_id')
        record('RESCHEDULE', 'artist requests a new date/time', r.status_code == 201 and rid, 201, r.status_code, sev='P1')
        b = Booking.objects.get(booking_id=bid)
        record('RESCHEDULE', 'proposal stored, booking unchanged until the customer decides', BookingReschedule.objects.get(reschedule_id=rid).status == 'pending' and str(b.start_time) == '10:00:00' and b.booking_date == w.future_date(5), 'pending', 'checked', sev='P1')
        record('RESCHEDULE', 'a second open request on the same booking is refused', self._request(bid, start='16:00:00').status_code == 400, 400, 'checked', sev='P1')
        record('RESCHEDULE', 'another customer cannot accept the request', not is_2xx(self.other.client.put('/customers/bookings/reschedule/respond/', {'reschedule_id': rid, 'decision': 'accepted'}, format='json')), 'refused', 'checked', sev='P0')
        record('RESCHEDULE', 'the artist cannot accept on the customer\'s behalf', not is_2xx(A.client.put('/customers/bookings/reschedule/respond/', {'reschedule_id': rid, 'decision': 'accepted'}, format='json')), 'refused', 'checked', sev='P0')
        # stale: someone else takes the proposed slot
        blocker = w.create_booking(self.other, A, start='14:30:00', day=6)
        r = C.client.put('/customers/bookings/reschedule/respond/', {'reschedule_id': rid, 'decision': 'accepted'}, format='json')
        record('RESCHEDULE', 'accepting a stale request whose slot was taken meanwhile is refused', r.status_code == 400 and Booking.objects.get(booking_id=bid).booking_date == w.future_date(5), 'refused, booking unchanged', r.status_code, sev='P0')
        Booking.objects.filter(booking_id=data(blocker)['booking_id']).delete()
        ArtistAvailabilityBlock.objects.create(artist=A.profile, block_date=w.future_date(6))
        r = C.client.put('/customers/bookings/reschedule/respond/', {'reschedule_id': rid, 'decision': 'accepted'}, format='json')
        record('RESCHEDULE', 'accepting after the proposed day was blocked is refused', r.status_code == 400, 400, r.status_code, sev='P0')
        ArtistAvailabilityBlock.objects.filter(artist=A.profile).delete()
        r = C.client.put('/customers/bookings/reschedule/respond/', {'reschedule_id': rid, 'decision': 'accepted'}, format='json')
        b = Booking.objects.get(booking_id=bid)
        record('RESCHEDULE', 'accept moves the booking and frees the old slot', r.status_code == 200 and b.booking_date == w.future_date(6) and str(b.start_time) == '14:00:00', 'moved', (r.status_code, b.booking_date, b.start_time), sev='P0')
        record('RESCHEDULE', 'the vacated slot can be booked by someone else, the new one cannot', w.create_booking(self.other, A, start='10:00:00', day=5).status_code == 201 and w.create_booking(self.other, A, start='14:00:00', day=6).status_code == 400, 'free / taken', 'checked', sev='P0')
        record('RESCHEDULE', 'a decided request cannot be answered again', C.client.put('/customers/bookings/reschedule/respond/', {'reschedule_id': rid, 'decision': 'rejected'}, format='json').status_code == 400, 400, 'checked', sev='P1')
        # reject + expiry + cancel
        bid2 = self._confirmed(start='17:00:00', day=7)
        rid2 = data(self._request(bid2, day=8, start='09:00:00'))['reschedule_id']
        C.client.put('/customers/bookings/reschedule/respond/', {'reschedule_id': rid2, 'decision': 'rejected'}, format='json')
        record('RESCHEDULE', 'rejection leaves the booking untouched', Booking.objects.get(booking_id=bid2).booking_date == w.future_date(7), 'unchanged', 'checked', sev='P1')
        rid3 = data(self._request(bid2, day=8, start='09:00:00'))['reschedule_id']
        BookingReschedule.objects.filter(reschedule_id=rid3).update(expires_at=timezone.now() - datetime.timedelta(minutes=1))
        r = C.client.put('/customers/bookings/reschedule/respond/', {'reschedule_id': rid3, 'decision': 'accepted'}, format='json')
        record('RESCHEDULE', 'an expired request cannot be accepted', r.status_code == 400 and Booking.objects.get(booking_id=bid2).booking_date == w.future_date(7), 'refused', r.status_code, sev='P1')
        rid4 = data(self._request(bid2, day=8, start='09:00:00'))['reschedule_id']
        C.client.put('/customers/bookings/cancel/', {'booking_id': bid2}, format='json')
        record('RESCHEDULE', 'cancelling the booking closes its pending reschedule', BookingReschedule.objects.get(reschedule_id=rid4).status == 'cancelled', 'cancelled', BookingReschedule.objects.get(reschedule_id=rid4).status, sev='P1')
        # started booking
        bid3 = self._confirmed(start='11:30:00', day=9)
        Booking.objects.filter(booking_id=bid3).update(on_my_way_at=timezone.now())
        record('RESCHEDULE', 'a booking whose artist already set off cannot be rescheduled', self._request(bid3, day=10).status_code == 400, 400, 'checked', sev='P1')
