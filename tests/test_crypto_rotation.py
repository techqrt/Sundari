from cryptography.fernet import Fernet
from django.test import SimpleTestCase, override_settings

from sunndari_apps.common.crypto import encrypt_text, decrypt_text


class EncryptionKeyRotationTest(SimpleTestCase):
    OLD, NEW = Fernet.generate_key().decode(), Fernet.generate_key().decode()

    def test_values_survive_a_key_rotation(self):
        with override_settings(FIELD_ENCRYPTION_KEY=self.OLD):
            token = encrypt_text('123456789012')
        with override_settings(FIELD_ENCRYPTION_KEY=f'{self.NEW},{self.OLD}'):       # new key first, old kept
            self.assertEqual(decrypt_text(token), '123456789012')
            fresh = encrypt_text('987654321098')
        with override_settings(FIELD_ENCRYPTION_KEY=self.NEW):                       # old key finally dropped
            self.assertEqual(decrypt_text(fresh), '987654321098')                    # new values use the new key
            self.assertIsNone(decrypt_text(token))                                   # and old ones are unreadable, never an error

    def test_a_single_key_and_the_derived_fallback_still_work(self):
        with override_settings(FIELD_ENCRYPTION_KEY=self.NEW):
            self.assertEqual(decrypt_text(encrypt_text('abc')), 'abc')
        with override_settings(FIELD_ENCRYPTION_KEY=''):
            self.assertEqual(decrypt_text(encrypt_text('abc')), 'abc')
