from django.test import TestCase

from sunndari_apps.core.models import ApprovalStatus

from tests.test_artists import make_authenticated_client, get_artist_profile, complete_onboarding_steps


def make_admin_client(phone_number='+919400000101'):
    return make_authenticated_client(phone_number=phone_number, role='admin')


def verify_id_proof(admin_client, artist_profile):
    """Approves the artist's ID proof through the real admin endpoints (list, then verify)."""
    for name in ('approved', 'rejected'):
        ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
    documents = admin_client.get(
        '/admin-panel/artists/documents/get_all/', {'artist_id': artist_profile.artist_id},
    ).data['data']
    id_proof = next(doc for doc in documents if doc['documentType'] == 'id_proof')
    resp = admin_client.put('/admin-panel/artists/documents/verify/', {
        'document_id': id_proof['documentId'], 'decision': 'approved',
    }, format='json')
    assert resp.status_code == 200, resp.data


# ─── Admin Artist Review — Access Control ──────────────────────────────────────

class AdminArtistReviewAccessTest(TestCase):
    queue_url = '/admin-panel/artists/review_queue/get_all/'
    approve_url = '/admin-panel/artists/approve/'
    reject_url = '/admin-panel/artists/reject/'

    def test_non_admin_review_queue_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919000000500')
        resp = client.get(self.queue_url)
        self.assertEqual(resp.status_code, 400)

    def test_non_admin_approve_returns_400(self):
        _, user = make_authenticated_client(phone_number='+919000000501')
        profile = get_artist_profile(user)
        client, _ = make_authenticated_client(phone_number='+919000000502')
        resp = client.put(self.approve_url, {'artist_id': profile.artist_id}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_review_queue_unauthenticated_returns_401(self):
        from rest_framework.test import APIClient
        resp = APIClient().get(self.queue_url)
        self.assertEqual(resp.status_code, 401)


# ─── Admin Artist Review — Queue Membership ────────────────────────────────────

class AdminArtistReviewQueueTest(TestCase):
    queue_url = '/admin-panel/artists/review_queue/get_all/'

    def test_review_queue_lists_only_submitted_artists(self):
        artist_client, artist_user = make_authenticated_client(phone_number='+919000000503')
        complete_onboarding_steps(artist_client, artist_user)
        artist_client.post('/artists/onboarding/submit/', {}, format='json')

        _, unsubmitted_user = make_authenticated_client(phone_number='+919000000504')

        admin_client, _ = make_admin_client(phone_number='+919400000102')
        resp = admin_client.get(self.queue_url)
        self.assertEqual(resp.status_code, 200)
        artist_ids = [row['artistId'] for row in resp.data['data']['data']]
        self.assertIn(get_artist_profile(artist_user).artist_id, artist_ids)
        self.assertNotIn(get_artist_profile(unsubmitted_user).artist_id, artist_ids)


# ─── Admin Artist Review — Approve / Reject ────────────────────────────────────

class AdminArtistApproveRejectTest(TestCase):
    approve_url = '/admin-panel/artists/approve/'
    reject_url = '/admin-panel/artists/reject/'
    queue_url = '/admin-panel/artists/review_queue/get_all/'

    def test_approve_unsubmitted_artist_returns_400(self):
        _, user = make_authenticated_client(phone_number='+919000000505')
        profile = get_artist_profile(user)
        admin_client, _ = make_admin_client(phone_number='+919400000103')
        resp = admin_client.put(self.approve_url, {'artist_id': profile.artist_id}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_approve_nonexistent_artist_returns_400(self):
        admin_client, _ = make_admin_client(phone_number='+919400000104')
        resp = admin_client.put(self.approve_url, {'artist_id': 999999}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_approve_submitted_artist_returns_200(self):
        ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        artist_client, artist_user = make_authenticated_client(phone_number='+919000000506')
        complete_onboarding_steps(artist_client, artist_user)
        artist_client.post('/artists/onboarding/submit/', {}, format='json')
        profile = get_artist_profile(artist_user)

        admin_client, _ = make_admin_client(phone_number='+919400000105')
        verify_id_proof(admin_client, profile)
        resp = admin_client.put(self.approve_url, {'artist_id': profile.artist_id}, format='json')
        self.assertEqual(resp.status_code, 200)
        profile.refresh_from_db()
        approved = ApprovalStatus.objects.get(name='approved')
        self.assertEqual(profile.approval_status_id, approved.status_id)

    def test_reject_submitted_artist_stores_reason_and_clears_submission(self):
        ApprovalStatus.objects.get_or_create(name='rejected', defaults={'description': 'Rejected'})
        artist_client, artist_user = make_authenticated_client(phone_number='+919000000507')
        complete_onboarding_steps(artist_client, artist_user)
        artist_client.post('/artists/onboarding/submit/', {}, format='json')
        profile = get_artist_profile(artist_user)

        admin_client, _ = make_admin_client(phone_number='+919400000106')
        resp = admin_client.put(self.reject_url, {
            'artist_id': profile.artist_id, 'reason': 'Blurry ID photo',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        profile.refresh_from_db()
        rejected = ApprovalStatus.objects.get(name='rejected')
        self.assertEqual(profile.approval_status_id, rejected.status_id)
        self.assertEqual(profile.rejection_reason, 'Blurry ID photo')
        self.assertIsNone(profile.submitted_for_review_at)

    def test_resubmission_after_rejection_reappears_in_queue(self):
        ApprovalStatus.objects.get_or_create(name='rejected', defaults={'description': 'Rejected'})
        artist_client, artist_user = make_authenticated_client(phone_number='+919000000508')
        complete_onboarding_steps(artist_client, artist_user)
        artist_client.post('/artists/onboarding/submit/', {}, format='json')
        profile = get_artist_profile(artist_user)

        admin_client, _ = make_admin_client(phone_number='+919400000107')
        admin_client.put(self.reject_url, {'artist_id': profile.artist_id, 'reason': 'Fix this'}, format='json')

        resp = admin_client.get(self.queue_url)
        artist_ids = [row['artistId'] for row in resp.data['data']['data']]
        self.assertNotIn(profile.artist_id, artist_ids, 'a rejected artist must not sit in the pending queue')

        artist_client.post('/artists/onboarding/submit/', {}, format='json')
        resp = admin_client.get(self.queue_url)
        artist_ids = [row['artistId'] for row in resp.data['data']['data']]
        self.assertIn(profile.artist_id, artist_ids, 'resubmission after rejection must re-enter the queue')

    def test_double_approve_is_idempotent(self):
        artist_client, artist_user = make_authenticated_client(phone_number='+919000000509')
        complete_onboarding_steps(artist_client, artist_user)
        artist_client.post('/artists/onboarding/submit/', {}, format='json')
        profile = get_artist_profile(artist_user)

        admin_client, _ = make_admin_client(phone_number='+919400000108')
        verify_id_proof(admin_client, profile)
        admin_client.put(self.approve_url, {'artist_id': profile.artist_id}, format='json')
        resp = admin_client.put(self.approve_url, {'artist_id': profile.artist_id}, format='json')
        self.assertEqual(resp.status_code, 200)


# ─── Admin Artist Review — suspended artists ───────────────────────────────────

class AdminSuspendedArtistTest(TestCase):
    approve_url = '/admin-panel/artists/approve/'
    reject_url = '/admin-panel/artists/reject/'

    def _suspended_submitted_artist(self, phone_number):
        from django.utils import timezone
        suspended, _ = ApprovalStatus.objects.get_or_create(name='suspended', defaults={'description': 'Suspended'})
        _, user = make_authenticated_client(phone_number=phone_number)
        profile = get_artist_profile(user)
        profile.approval_status = suspended
        profile.submitted_for_review_at = timezone.now()
        profile.save()
        return profile, suspended

    def test_approve_suspended_artist_returns_400_and_keeps_suspension(self):
        profile, suspended = self._suspended_submitted_artist('+919000000520')
        admin_client, _ = make_admin_client(phone_number='+919400000120')
        resp = admin_client.put(self.approve_url, {'artist_id': profile.artist_id}, format='json')
        self.assertEqual(resp.status_code, 400)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status_id, suspended.status_id)

    def test_reject_suspended_artist_returns_400_and_keeps_suspension(self):
        profile, suspended = self._suspended_submitted_artist('+919000000521')
        admin_client, _ = make_admin_client(phone_number='+919400000121')
        resp = admin_client.put(self.reject_url, {'artist_id': profile.artist_id, 'reason': 'x'}, format='json')
        self.assertEqual(resp.status_code, 400)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status_id, suspended.status_id)


# ─── Admin KYC document review ─────────────────────────────────────────────────

class AdminKycDocumentReviewTest(TestCase):
    list_url = '/admin-panel/artists/documents/get_all/'
    verify_url = '/admin-panel/artists/documents/verify/'
    approve_url = '/admin-panel/artists/approve/'

    def setUp(self):
        for name in ('approved', 'rejected'):
            ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
        self.artist_client, self.artist_user = make_authenticated_client(phone_number='+919000000700')
        complete_onboarding_steps(self.artist_client, self.artist_user)
        self.artist_client.post('/artists/onboarding/submit/', {}, format='json')
        self.profile = get_artist_profile(self.artist_user)
        self.admin_client, _ = make_admin_client(phone_number='+919400000130')

    def _document_id(self):
        return self.admin_client.get(self.list_url, {'artist_id': self.profile.artist_id}).data['data'][0]['documentId']

    def test_non_admin_cannot_list_or_verify(self):
        resp = self.artist_client.get(self.list_url, {'artist_id': self.profile.artist_id})
        self.assertEqual(resp.status_code, 400)
        resp = self.artist_client.put(self.verify_url, {'document_id': self._document_id(), 'decision': 'approved'},
                                      format='json')
        self.assertEqual(resp.status_code, 400)

    def test_admin_sees_full_passport_number_but_artist_api_stays_masked(self):
        listed = self.admin_client.get(self.list_url, {'artist_id': self.profile.artist_id}).data['data'][0]
        self.assertEqual(listed['idType'], 'passport')
        self.assertEqual(listed['idNumber'], 'K1234567')
        self.assertEqual(listed['documentNumber'], 'XXXXXXXX'[:4] + '4567')
        own = self.artist_client.get('/artists/documents/get_all/').data['data']['data'][0]
        self.assertNotIn('K1234567', str(own))
        self.assertEqual(own['documentNumber'], 'XXXX4567')

    def test_approve_artist_requires_verified_id_proof(self):
        resp = self.admin_client.put(self.approve_url, {'artist_id': self.profile.artist_id}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.profile.refresh_from_db()
        self.assertNotEqual(self.profile.approval_status.name, 'approved')

    def test_rejected_document_does_not_unlock_approval_and_reason_reaches_artist(self):
        resp = self.admin_client.put(self.verify_url, {
            'document_id': self._document_id(), 'decision': 'rejected', 'reason': 'Photo is blurry',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        own = self.artist_client.get('/artists/documents/get_all/').data['data']['data'][0]
        self.assertEqual(own['rejectionReason'], 'Photo is blurry')
        resp = self.admin_client.put(self.approve_url, {'artist_id': self.profile.artist_id}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_reject_requires_reason(self):
        resp = self.admin_client.put(self.verify_url, {'document_id': self._document_id(), 'decision': 'rejected'},
                                     format='json')
        self.assertEqual(resp.status_code, 400)

    def test_decision_is_final_and_notifies_artist(self):
        from sunndari_apps.notifications.models.notification import Notification
        document_id = self._document_id()
        payload = {'document_id': document_id, 'decision': 'approved'}
        self.assertEqual(self.admin_client.put(self.verify_url, payload, format='json').status_code, 200)
        self.assertEqual(self.admin_client.put(self.verify_url, payload, format='json').status_code, 400)
        self.assertTrue(Notification.objects.filter(user_id=self.artist_user.user_id, type='document_approved').exists())

    def test_resubmitting_id_proof_resets_verification_and_replaces_old_document(self):
        from tests.test_artists import ID_PROOF_FORM, make_image_bytes
        from django.core.files.uploadedfile import SimpleUploadedFile
        verify_id_proof(self.admin_client, self.profile)
        resp = self.artist_client.post('/artists/documents/create/', {
            **ID_PROOF_FORM, 'document_number': 'L7654321',
            'file': SimpleUploadedFile('new.png', make_image_bytes('PNG'), content_type='image/png'),
        }, format='multipart')
        self.assertEqual(resp.status_code, 201)
        documents = self.admin_client.get(self.list_url, {'artist_id': self.profile.artist_id}).data['data']
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]['verificationStatus'], 'pending')
        resp = self.admin_client.put(self.approve_url, {'artist_id': self.profile.artist_id}, format='json')
        self.assertEqual(resp.status_code, 400)


# ─── Admin review detail ───────────────────────────────────────────────────────

class AdminReviewDetailTest(TestCase):
    url = '/admin-panel/artists/review/get/'

    def test_admin_sees_registration_fields_and_work_samples(self):
        artist_client, artist_user = make_authenticated_client(phone_number='+919000000710')
        complete_onboarding_steps(artist_client, artist_user)
        profile = get_artist_profile(artist_user)
        admin_client, _ = make_admin_client(phone_number='+919400000140')
        data = admin_client.get(self.url, {'artist_id': profile.artist_id}).data['data']
        self.assertEqual(data['displayName'], 'Glam by Test')
        self.assertEqual(data['dateOfBirth'], '1995-05-20')
        self.assertEqual(data['profileType'], 'freelance')
        self.assertEqual(len(data['workSamples']), 1)
        self.assertTrue(data['workSamples'][0]['fileUrl'])
        self.assertEqual(data['fullName'], 'Test Artist')

    def test_non_admin_and_unknown_artist_refused(self):
        client, user = make_authenticated_client(phone_number='+919000000711')
        profile = get_artist_profile(user)
        self.assertEqual(client.get(self.url, {'artist_id': profile.artist_id}).status_code, 400)
        admin_client, _ = make_admin_client(phone_number='+919400000141')
        self.assertEqual(admin_client.get(self.url, {'artist_id': 999999}).status_code, 400)


# ─── Review feedback history ───────────────────────────────────────────────────

class ReviewFeedbackHistoryTest(TestCase):
    feedback_url = '/artists/review/feedback/get_all/'
    status_url = '/artists/onboarding/status/'
    approve_url = '/admin-panel/artists/approve/'
    reject_url = '/admin-panel/artists/reject/'

    def setUp(self):
        for name in ('approved', 'rejected'):
            ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
        self.client_a, self.user_a = make_authenticated_client(phone_number='+919000000750')
        complete_onboarding_steps(self.client_a, self.user_a)
        self.client_a.post('/artists/onboarding/submit/', {}, format='json')
        self.profile = get_artist_profile(self.user_a)
        self.admin, _ = make_admin_client(phone_number='+919400000150')

    def test_no_feedback_before_any_decision(self):
        self.assertEqual(self.client_a.get(self.feedback_url).data['data']['data'], [])
        self.assertIsNone(self.client_a.get(self.status_url).data['data']['latestFeedback'])

    def test_every_round_of_feedback_is_kept(self):
        self.admin.put(self.reject_url, {'artist_id': self.profile.artist_id, 'reason': 'Round 1: blurry'}, format='json')
        self.client_a.post('/artists/onboarding/submit/', {}, format='json')
        self.admin.put(self.reject_url, {'artist_id': self.profile.artist_id, 'reason': 'Round 2: wrong city'}, format='json')
        listed = self.client_a.get(self.feedback_url).data['data']['data']
        self.assertEqual([row['message'] for row in listed], ['Round 1: blurry', 'Round 2: wrong city'])
        self.assertTrue(all(row['decision'] == 'rejected' for row in listed))
        newest_first = self.client_a.get(self.feedback_url, {'sort_order': 'desc'}).data['data']['data']
        self.assertEqual(newest_first[0]['message'], 'Round 2: wrong city')

    def test_status_stays_rejected_and_exposes_latest_feedback(self):
        self.admin.put(self.reject_url, {'artist_id': self.profile.artist_id, 'reason': 'Fix photo'}, format='json')
        data = self.client_a.get(self.status_url).data['data']
        self.assertEqual(data['status'], 'rejected')
        self.assertEqual(data['latestFeedback']['message'], 'Fix photo')
        self.assertEqual(data['latestFeedback']['decision'], 'rejected')

    def test_approval_with_message_is_recorded_and_notified(self):
        from sunndari_apps.notifications.models.notification import Notification
        verify_id_proof(self.admin, self.profile)
        self.admin.put(self.approve_url, {'artist_id': self.profile.artist_id, 'message': 'Welcome aboard'}, format='json')
        latest = self.client_a.get(self.status_url).data['data']
        self.assertEqual(latest['status'], 'approved')
        self.assertEqual(latest['latestFeedback']['decision'], 'approved')
        self.assertEqual(latest['latestFeedback']['message'], 'Welcome aboard')
        self.assertTrue(Notification.objects.filter(user_id=self.user_a.user_id, type='artist_approved').exists())

    def test_rejection_notifies_artist_with_reason(self):
        from sunndari_apps.notifications.models.notification import Notification
        self.admin.put(self.reject_url, {'artist_id': self.profile.artist_id, 'reason': 'Needs clearer ID'}, format='json')
        note = Notification.objects.get(user_id=self.user_a.user_id, type='artist_rejected')
        self.assertIn('Needs clearer ID', note.message)

    def test_failed_admin_action_records_nothing(self):
        other_client, other_user = make_authenticated_client(phone_number='+919000000751')
        non_admin_resp = other_client.put(self.reject_url, {'artist_id': self.profile.artist_id, 'reason': 'x'}, format='json')
        self.assertEqual(non_admin_resp.status_code, 400)
        self.assertEqual(self.client_a.get(self.feedback_url).data['data']['data'], [])
        # approval without a verified ID proof is refused and leaves no "approved" record either
        self.admin.put(self.approve_url, {'artist_id': self.profile.artist_id}, format='json')
        self.assertEqual(self.client_a.get(self.feedback_url).data['data']['data'], [])

    def test_artist_only_sees_own_feedback_and_auth_required(self):
        self.admin.put(self.reject_url, {'artist_id': self.profile.artist_id, 'reason': 'Private note'}, format='json')
        other_client, _ = make_authenticated_client(phone_number='+919000000752')
        self.assertEqual(other_client.get(self.feedback_url).data['data']['data'], [])
        from rest_framework.test import APIClient
        self.assertEqual(APIClient().get(self.feedback_url).status_code, 401)
