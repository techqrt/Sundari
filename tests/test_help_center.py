from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.help_center.models import SupportConversation, SupportMessage
from sunndari_apps.notifications.models.notification import Notification

from tests.test_customers import make_user, make_client, make_customer, make_artist


def make_admin(phone_number='+919400000001', name='Test Admin'):
    user = make_user(phone_number, 'admin', name)
    return make_client(user), user


# ─── HTTP: Customer conversation & authorization ──────────────────────────────

class CustomerConversationTest(TestCase):

    def test_no_conversation_before_first_message(self):
        client, _ = make_customer(phone_number='+919300000001')
        resp = client.get('/help_center/conversation/get/')
        self.assertEqual(resp.status_code, 400)

    def test_conversation_created_on_first_message(self):
        client, customer = make_customer(phone_number='+919300000002')
        resp = client.post('/help_center/messages/create/', {'content': 'Hello support'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(SupportConversation.objects.filter(customer_id=customer.user_id).exists())

    def test_conversation_reused_for_second_message(self):
        client, customer = make_customer(phone_number='+919300000003')
        client.post('/help_center/messages/create/', {'content': 'first'}, format='json')
        client.post('/help_center/messages/create/', {'content': 'second'}, format='json')
        self.assertEqual(SupportConversation.objects.filter(customer_id=customer.user_id).count(), 1)

    def test_customer_can_get_own_conversation(self):
        client, customer = make_customer(phone_number='+919300000004')
        client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        resp = client.get('/help_center/conversation/get/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['customerId'], customer.user_id)
        self.assertEqual(resp.data['data']['status'], 'open')

    def test_anonymous_user_cannot_access_help_center(self):
        resp = APIClient().get('/help_center/conversation/get/')
        self.assertEqual(resp.status_code, 401)

    def test_empty_message_rejected(self):
        client, _ = make_customer(phone_number='+919300000005')
        resp = client.post('/help_center/messages/create/', {'content': '   '}, format='json')
        self.assertEqual(resp.status_code, 400)


# ─── HTTP: Message history & pagination ───────────────────────────────────────

class MessageHistoryTest(TestCase):

    def test_message_history_ordered(self):
        client, customer = make_customer(phone_number='+919300000101')
        admin_client, _ = make_admin(phone_number='+919300000102')
        client.post('/help_center/messages/create/', {'content': 'first'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        admin_client.post(
            '/help_center/admin/messages/create/',
            {'conversation_id': conversation.conversation_id, 'content': 'second'}, format='json',
        )
        resp = client.get('/help_center/messages/get_all/', {'conversation_id': conversation.conversation_id})
        self.assertEqual(resp.status_code, 200)
        contents = [m['content'] for m in resp.data['data']['data']]
        self.assertEqual(contents, ['first', 'second'])

    def test_customer_cannot_read_another_customers_messages(self):
        client_a, customer_a = make_customer(phone_number='+919300000103')
        client_b, _ = make_customer(phone_number='+919300000104')
        client_a.post('/help_center/messages/create/', {'content': 'private'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer_a.user_id)
        resp = client_b.get('/help_center/messages/get_all/', {'conversation_id': conversation.conversation_id})
        self.assertEqual(resp.status_code, 400)

    def test_message_is_persisted(self):
        client, customer = make_customer(phone_number='+919300000105')
        client.post('/help_center/messages/create/', {'content': 'persist me'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        self.assertTrue(SupportMessage.objects.filter(conversation=conversation, content='persist me').exists())


# ─── HTTP: Status lifecycle (open → running → closed) ─────────────────────────

class ConversationLifecycleTest(TestCase):

    def test_conversation_starts_open(self):
        client, customer = make_customer(phone_number='+919300000201')
        client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        self.assertEqual(conversation.status, 'open')

    def test_conversation_moves_to_running_on_first_admin_reply(self):
        client, customer = make_customer(phone_number='+919300000202')
        admin_client, _ = make_admin(phone_number='+919300000203')
        client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        admin_client.post(
            '/help_center/admin/messages/create/',
            {'conversation_id': conversation.conversation_id, 'content': 'how can I help?'}, format='json',
        )
        conversation.refresh_from_db()
        self.assertEqual(conversation.status, 'running')

    def test_non_admin_cannot_reply(self):
        client, customer = make_customer(phone_number='+919300000204')
        other_customer_client, _ = make_customer(phone_number='+919300000205')
        client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        resp = other_customer_client.post(
            '/help_center/admin/messages/create/',
            {'conversation_id': conversation.conversation_id, 'content': 'sneaky'}, format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_admin_can_close_conversation(self):
        client, customer = make_customer(phone_number='+919300000206')
        admin_client, _ = make_admin(phone_number='+919300000207')
        client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        resp = admin_client.post(
            '/help_center/admin/conversation/close/', {'conversation_id': conversation.conversation_id}, format='json',
        )
        self.assertEqual(resp.status_code, 200)
        conversation.refresh_from_db()
        self.assertEqual(conversation.status, 'closed')

    def test_customer_cannot_close_conversation(self):
        client, customer = make_customer(phone_number='+919300000208')
        client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        resp = client.post(
            '/help_center/admin/conversation/close/', {'conversation_id': conversation.conversation_id}, format='json',
        )
        self.assertEqual(resp.status_code, 400)
        conversation.refresh_from_db()
        self.assertEqual(conversation.status, 'open')

    def test_customer_conversation_not_reachable_right_after_close(self):
        client, customer = make_customer(phone_number='+919300000209')
        admin_client, _ = make_admin(phone_number='+919300000210')
        client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        admin_client.post(
            '/help_center/admin/conversation/close/', {'conversation_id': conversation.conversation_id}, format='json',
        )
        resp = client.get('/help_center/conversation/get/')
        self.assertEqual(resp.status_code, 400)

    def test_new_message_after_close_starts_a_new_conversation(self):
        client, customer = make_customer(phone_number='+919300000211')
        admin_client, _ = make_admin(phone_number='+919300000212')
        client.post('/help_center/messages/create/', {'content': 'first ticket'}, format='json')
        first_conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        admin_client.post(
            '/help_center/admin/conversation/close/',
            {'conversation_id': first_conversation.conversation_id}, format='json',
        )
        resp = client.post('/help_center/messages/create/', {'content': 'second ticket'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(SupportConversation.objects.filter(customer_id=customer.user_id).count(), 2)
        new_conversation = SupportConversation.objects.exclude(
            conversation_id=first_conversation.conversation_id,
        ).get(customer_id=customer.user_id)
        self.assertEqual(new_conversation.status, 'open')


# ─── HTTP: Admin conversation dashboard ────────────────────────────────────────

class AdminConversationListTest(TestCase):

    def test_admin_can_list_conversations_filtered_by_status(self):
        client, customer = make_customer(phone_number='+919300000401')
        admin_client, _ = make_admin(phone_number='+919300000402')
        client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        resp = admin_client.get('/help_center/admin/conversations/get_all/', {'status': 'open'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)
        self.assertEqual(resp.data['data']['data'][0]['customerId'], customer.user_id)

    def test_customer_cannot_list_admin_conversations(self):
        client, _ = make_customer(phone_number='+919300000403')
        resp = client.get('/help_center/admin/conversations/get_all/')
        self.assertEqual(resp.status_code, 400)

    def test_admin_can_get_single_conversation(self):
        client, customer = make_customer(phone_number='+919300000404')
        admin_client, _ = make_admin(phone_number='+919300000405')
        client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        resp = admin_client.get(
            '/help_center/admin/conversation/get/', {'conversation_id': conversation.conversation_id},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['conversationId'], conversation.conversation_id)

    def test_customer_cannot_get_admin_conversation_view(self):
        client, customer = make_customer(phone_number='+919300000406')
        client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        resp = client.get(
            '/help_center/admin/conversation/get/', {'conversation_id': conversation.conversation_id},
        )
        self.assertEqual(resp.status_code, 400)


# ─── Notification integration ─────────────────────────────────────────────────

class NotificationIntegrationTest(TestCase):

    def test_customer_message_notifies_all_admins(self):
        client, _ = make_customer(phone_number='+919300000501')
        _, admin_user = make_admin(phone_number='+919300000502')
        client.post('/help_center/messages/create/', {'content': 'need help'}, format='json')
        self.assertTrue(
            Notification.objects.filter(user_id=admin_user.user_id, type='help_center_customer_message').exists()
        )

    def test_admin_reply_notifies_customer(self):
        client, customer = make_customer(phone_number='+919300000503')
        admin_client, _ = make_admin(phone_number='+919300000504')
        client.post('/help_center/messages/create/', {'content': 'need help'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=customer.user_id)
        admin_client.post(
            '/help_center/admin/messages/create/',
            {'conversation_id': conversation.conversation_id, 'content': 'sure, one sec'}, format='json',
        )
        self.assertTrue(
            Notification.objects.filter(user_id=customer.user_id, type='help_center_admin_reply').exists()
        )


# ─── HTTP: Artist support endpoints (same model, separate routes) ─────────────

class ArtistSupportEndpointTest(TestCase):

    def test_artist_can_create_and_read_own_conversation(self):
        client, artist, _ = make_artist(phone_number='+919300000601')
        resp = client.post('/help_center/artist/messages/create/', {'content': 'payout question'}, format='json')
        self.assertEqual(resp.status_code, 201)
        conversation = SupportConversation.objects.get(customer_id=artist.user_id)
        self.assertEqual(conversation.status, 'open')

        get_resp = client.get('/help_center/artist/conversation/get/')
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.data['data']['role'], 'artist')

    def test_artist_message_history_via_artist_route(self):
        client, artist, _ = make_artist(phone_number='+919300000602')
        admin_client, _ = make_admin(phone_number='+919300000603')
        client.post('/help_center/artist/messages/create/', {'content': 'first'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=artist.user_id)
        admin_client.post(
            '/help_center/admin/messages/create/',
            {'conversation_id': conversation.conversation_id, 'content': 'second'}, format='json',
        )
        resp = client.get(
            '/help_center/artist/messages/get_all/', {'conversation_id': conversation.conversation_id},
        )
        self.assertEqual(resp.status_code, 200)
        contents = [m['content'] for m in resp.data['data']['data']]
        self.assertEqual(contents, ['first', 'second'])

    def test_artist_message_notifies_admin_with_artist_type(self):
        client, artist, _ = make_artist(phone_number='+919300000604')
        _, admin_user = make_admin(phone_number='+919300000605')
        client.post('/help_center/artist/messages/create/', {'content': 'payout question'}, format='json')
        self.assertTrue(
            Notification.objects.filter(user_id=admin_user.user_id, type='help_center_artist_message').exists()
        )
        self.assertFalse(
            Notification.objects.filter(user_id=admin_user.user_id, type='help_center_customer_message').exists()
        )

    def test_customer_cannot_read_artist_conversation_by_id(self):
        artist_client, artist, _ = make_artist(phone_number='+919300000606')
        artist_client.post('/help_center/artist/messages/create/', {'content': 'payout question'}, format='json')
        conversation = SupportConversation.objects.get(customer_id=artist.user_id)
        customer_client, _ = make_customer(phone_number='+919300000607')
        resp = customer_client.get(
            '/help_center/messages/get_all/', {'conversation_id': conversation.conversation_id},
        )
        self.assertEqual(resp.status_code, 400)


# ─── HTTP: Admin role visibility & filtering ──────────────────────────────────

class AdminRoleFilterTest(TestCase):

    def test_conversation_list_reports_role_per_conversation(self):
        customer_client, _ = make_customer(phone_number='+919300000701')
        artist_client, _, _ = make_artist(phone_number='+919300000702')
        admin_client, _ = make_admin(phone_number='+919300000703')
        customer_client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        artist_client.post('/help_center/artist/messages/create/', {'content': 'hi'}, format='json')

        resp = admin_client.get('/help_center/admin/conversations/get_all/', {'status': 'open'})
        self.assertEqual(resp.status_code, 200)
        roles = sorted(c['role'] for c in resp.data['data']['data'])
        self.assertEqual(roles, ['artist', 'customer'])

    def test_admin_can_filter_conversations_by_role(self):
        customer_client, _ = make_customer(phone_number='+919300000704')
        artist_client, _, _ = make_artist(phone_number='+919300000705')
        admin_client, _ = make_admin(phone_number='+919300000706')
        customer_client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        artist_client.post('/help_center/artist/messages/create/', {'content': 'hi'}, format='json')

        artist_only = admin_client.get(
            '/help_center/admin/conversations/get_all/', {'status': 'open', 'role': 'artist'},
        )
        self.assertEqual(artist_only.status_code, 200)
        self.assertEqual(len(artist_only.data['data']['data']), 1)
        self.assertEqual(artist_only.data['data']['data'][0]['role'], 'artist')

        no_filter = admin_client.get(
            '/help_center/admin/conversations/get_all/', {'status': 'open', 'role': ''},
        )
        self.assertEqual(no_filter.status_code, 200)
        self.assertEqual(len(no_filter.data['data']['data']), 2)
