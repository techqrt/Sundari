from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from sunndari_apps.authentication.utils import generate_jwt_token
from sunndari_apps.chat.models import Conversation, Message
from sunndari_apps.customers.models import Booking

from tests.test_customers import (
    make_customer, make_artist, make_sub_category, make_location_type,
    make_package, make_booking, next_weekday,
)

IN_MEMORY_LAYER = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}


def auth(user):
    """Same token generation as make_client(), but returns the raw token too
    so it can be reused on a WS query string alongside the REST client."""
    token = generate_jwt_token(user)
    user.access_token = token
    user.save()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client, token


def confirmed_booking(customer_phone, artist_phone, status_name='confirmed'):
    _, customer = make_customer(phone_number=customer_phone)
    _, artist_user, profile = make_artist(phone_number=artist_phone)
    sub = make_sub_category()
    package = make_package(profile, sub_category=sub)
    location_type = make_location_type()
    booking = make_booking(
        customer, profile, package, location_type,
        booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        status_name=status_name,
    )
    return customer, artist_user, booking


# ─── HTTP: Conversation access & authorization ────────────────────────────────

class ConversationAccessTest(TestCase):

    def test_customer_can_access_own_booking_chat(self):
        customer, artist_user, booking = confirmed_booking('+919100000001', '+919100000002')
        client, _ = auth(customer)
        resp = client.get('/chat/conversation/get/', {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['bookingId'], booking.booking_id)

    def test_artist_can_access_own_booking_chat(self):
        customer, artist_user, booking = confirmed_booking('+919100000003', '+919100000004')
        client, _ = auth(artist_user)
        resp = client.get('/chat/conversation/get/', {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['bookingId'], booking.booking_id)

    def test_unrelated_customer_cannot_access_chat(self):
        customer, artist_user, booking = confirmed_booking('+919100000005', '+919100000006')
        outsider, _ = make_customer(phone_number='+919100000007')
        resp = outsider.get('/chat/conversation/get/', {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 400)

    def test_unrelated_artist_cannot_access_chat(self):
        customer, artist_user, booking = confirmed_booking('+919100000008', '+919100000009')
        outsider_client, _, _ = make_artist(phone_number='+919100000010')
        resp = outsider_client.get('/chat/conversation/get/', {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 400)

    def test_anonymous_user_cannot_access_chat(self):
        _, _, booking = confirmed_booking('+919100000011', '+919100000012')
        resp = APIClient().get('/chat/conversation/get/', {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 401)

    def test_pending_booking_not_eligible_for_chat(self):
        customer, _, booking = confirmed_booking('+919100000013', '+919100000014', status_name='pending')
        client, _ = auth(customer)
        resp = client.get('/chat/conversation/get/', {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 400)

    def test_conversation_not_duplicated_for_same_booking(self):
        customer, artist_user, booking = confirmed_booking('+919100000015', '+919100000016')
        client, _ = auth(customer)
        first = client.get('/chat/conversation/get/', {'booking_id': booking.booking_id})
        second = client.get('/chat/conversation/get/', {'booking_id': booking.booking_id})
        self.assertEqual(first.data['data']['conversationId'], second.data['data']['conversationId'])
        self.assertEqual(Conversation.objects.filter(booking_id=booking.booking_id).count(), 1)

    def test_cannot_access_another_bookings_conversation_by_id_manipulation(self):
        customer_a, _, booking_a = confirmed_booking('+919100000017', '+919100000018')
        customer_b, _, booking_b = confirmed_booking('+919100000019', '+919100000020')
        client_a, _ = auth(customer_a)
        client_a.get('/chat/conversation/get/', {'booking_id': booking_a.booking_id})
        resp = client_a.get('/chat/messages/get_all/', {'booking_id': booking_b.booking_id})
        self.assertEqual(resp.status_code, 400)


# ─── HTTP: Messaging & persistence ────────────────────────────────────────────

class MessageEndpointTest(TestCase):

    def test_customer_can_send_message_while_eligible(self):
        customer, artist_user, booking = confirmed_booking('+919100000101', '+919100000102')
        client, _ = auth(customer)
        resp = client.post('/chat/messages/create/', {'booking_id': booking.booking_id, 'content': 'Hi there'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['data']['content'], 'Hi there')
        self.assertEqual(resp.data['data']['senderId'], customer.user_id)

    def test_artist_can_send_message_while_eligible(self):
        customer, artist_user, booking = confirmed_booking('+919100000103', '+919100000104')
        client, _ = auth(artist_user)
        resp = client.post('/chat/messages/create/', {'booking_id': booking.booking_id, 'content': 'On my way'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['data']['senderId'], artist_user.user_id)

    def test_message_is_persisted(self):
        customer, artist_user, booking = confirmed_booking('+919100000105', '+919100000106')
        client, _ = auth(customer)
        client.post('/chat/messages/create/', {'booking_id': booking.booking_id, 'content': 'Persist me'}, format='json')
        conversation = Conversation.objects.get(booking_id=booking.booking_id)
        self.assertTrue(Message.objects.filter(conversation=conversation, content='Persist me').exists())

    def test_message_history_retrieval_ordered(self):
        customer, artist_user, booking = confirmed_booking('+919100000107', '+919100000108')
        client, _ = auth(customer)
        artist_client, _ = auth(artist_user)
        client.post('/chat/messages/create/', {'booking_id': booking.booking_id, 'content': 'first'}, format='json')
        artist_client.post('/chat/messages/create/', {'booking_id': booking.booking_id, 'content': 'second'}, format='json')
        resp = client.get('/chat/messages/get_all/', {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 200)
        contents = [m['content'] for m in resp.data['data']['data']]
        self.assertEqual(contents, ['first', 'second'])

    def test_empty_message_rejected(self):
        customer, artist_user, booking = confirmed_booking('+919100000109', '+919100000110')
        client, _ = auth(customer)
        resp = client.post('/chat/messages/create/', {'booking_id': booking.booking_id, 'content': '   '}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_unrelated_user_cannot_send_message(self):
        customer, artist_user, booking = confirmed_booking('+919100000111', '+919100000112')
        outsider, _ = make_customer(phone_number='+919100000113')
        resp = outsider.post('/chat/messages/create/', {'booking_id': booking.booking_id, 'content': 'sneaky'}, format='json')
        self.assertEqual(resp.status_code, 400)


# ─── HTTP: Appointment completion closes chat ─────────────────────────────────

class ChatClosureTest(TestCase):

    def test_completed_booking_rejects_new_customer_message(self):
        customer, artist_user, booking = confirmed_booking('+919100000201', '+919100000202', status_name='in_progress')
        client, _ = auth(customer)
        client.post('/chat/messages/create/', {'booking_id': booking.booking_id, 'content': 'before completion'}, format='json')
        artist_client, _ = auth(artist_user)
        artist_client.put('/artists/bookings/update_status/', {'booking_id': booking.booking_id, 'status': 'completed'}, format='json')
        resp = client.post('/chat/messages/create/', {'booking_id': booking.booking_id, 'content': 'after completion'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_completed_booking_rejects_new_artist_message(self):
        customer, artist_user, booking = confirmed_booking('+919100000203', '+919100000204', status_name='in_progress')
        artist_client, _ = auth(artist_user)
        artist_client.put('/artists/bookings/update_status/', {'booking_id': booking.booking_id, 'status': 'completed'}, format='json')
        resp = artist_client.post('/chat/messages/create/', {'booking_id': booking.booking_id, 'content': 'too late'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_existing_messages_remain_readable_after_completion(self):
        customer, artist_user, booking = confirmed_booking('+919100000205', '+919100000206', status_name='in_progress')
        client, _ = auth(customer)
        client.post('/chat/messages/create/', {'booking_id': booking.booking_id, 'content': 'keep me'}, format='json')
        artist_client, _ = auth(artist_user)
        artist_client.put('/artists/bookings/update_status/', {'booking_id': booking.booking_id, 'status': 'completed'}, format='json')
        resp = client.get('/chat/messages/get_all/', {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['data'][0]['content'], 'keep me')


# ─── WebSocket ─────────────────────────────────────────────────────────────────

@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class ChatWebsocketTest(TransactionTestCase):

    async def _connect(self, booking_id, token):
        from channels.testing import WebsocketCommunicator
        from sunndari.asgi import application
        communicator = WebsocketCommunicator(application, f'/ws/chat/{booking_id}/?token={token}')
        connected, _ = await communicator.connect()
        return communicator, connected

    async def test_customer_and_artist_receive_each_others_messages(self):
        from channels.db import database_sync_to_async
        customer, artist_user, booking = await database_sync_to_async(confirmed_booking)('+919100000301', '+919100000302')
        _, customer_token = await database_sync_to_async(auth)(customer)
        _, artist_token = await database_sync_to_async(auth)(artist_user)

        customer_ws, customer_connected = await self._connect(booking.booking_id, customer_token)
        artist_ws, artist_connected = await self._connect(booking.booking_id, artist_token)
        self.assertTrue(customer_connected)
        self.assertTrue(artist_connected)

        await customer_ws.send_json_to({'type': 'message.send', 'content': 'Hello artist'})

        customer_echo = await customer_ws.receive_json_from()
        self.assertEqual(customer_echo['type'], 'message.created')
        self.assertEqual(customer_echo['message']['content'], 'Hello artist')

        artist_received = await artist_ws.receive_json_from()
        self.assertEqual(artist_received['type'], 'message.created')
        self.assertEqual(artist_received['message']['content'], 'Hello artist')

        await artist_ws.send_json_to({'type': 'message.send', 'content': 'On my way'})
        reply = await customer_ws.receive_json_from()
        self.assertEqual(reply['message']['content'], 'On my way')

        await customer_ws.disconnect()
        await artist_ws.disconnect()

    async def test_unrelated_user_rejected_on_connect(self):
        from channels.db import database_sync_to_async
        _, _, booking = await database_sync_to_async(confirmed_booking)('+919100000303', '+919100000304')
        outsider_client, outsider_user = await database_sync_to_async(make_customer)(phone_number='+919100000305')
        _, outsider_token = await database_sync_to_async(auth)(outsider_user)
        communicator, connected = await self._connect(booking.booking_id, outsider_token)
        self.assertFalse(connected)

    async def test_anonymous_connection_rejected(self):
        from channels.db import database_sync_to_async
        _, _, booking = await database_sync_to_async(confirmed_booking)('+919100000306', '+919100000307')
        communicator, connected = await self._connect(booking.booking_id, 'not-a-real-token')
        self.assertFalse(connected)

    async def test_two_bookings_do_not_cross_talk(self):
        from channels.db import database_sync_to_async
        customer1, artist1, booking1 = await database_sync_to_async(confirmed_booking)('+919100000308', '+919100000309')
        customer2, artist2, booking2 = await database_sync_to_async(confirmed_booking)('+919100000310', '+919100000311')
        _, token1 = await database_sync_to_async(auth)(customer1)
        _, token2 = await database_sync_to_async(auth)(customer2)

        ws1, connected1 = await self._connect(booking1.booking_id, token1)
        ws2, connected2 = await self._connect(booking2.booking_id, token2)
        self.assertTrue(connected1)
        self.assertTrue(connected2)

        await ws1.send_json_to({'type': 'message.send', 'content': 'booking1 only'})
        echo1 = await ws1.receive_json_from()
        self.assertEqual(echo1['message']['content'], 'booking1 only')
        self.assertTrue(await ws2.receive_nothing(timeout=0.2))

        await ws1.disconnect()
        await ws2.disconnect()

    async def test_stale_connection_cannot_send_after_completion(self):
        from channels.db import database_sync_to_async
        customer, artist_user, booking = await database_sync_to_async(confirmed_booking)(
            '+919100000312', '+919100000313', status_name='in_progress',
        )
        _, customer_token = await database_sync_to_async(auth)(customer)
        customer_ws, connected = await self._connect(booking.booking_id, customer_token)
        self.assertTrue(connected)

        def complete_booking():
            completed = Booking.objects.get(booking_id=booking.booking_id)
            from sunndari_apps.core.models.booking_status import BookingStatus
            completed.status = BookingStatus.objects.get(name='completed')
            completed.save()

        await database_sync_to_async(complete_booking)()

        await customer_ws.send_json_to({'type': 'message.send', 'content': 'too late'})
        response = await customer_ws.receive_json_from()
        self.assertEqual(response['type'], 'message.rejected')
        self.assertEqual(response['reason'], 'conversation_closed')

        await customer_ws.disconnect()
