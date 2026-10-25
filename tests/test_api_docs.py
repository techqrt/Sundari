import tempfile
from django.core.management import call_command
from django.test import SimpleTestCase


class ApiDocsTest(SimpleTestCase):

    def test_the_api_schema_generates_with_no_warnings_or_errors(self):
        with tempfile.NamedTemporaryFile(suffix='.yml') as out:
            call_command('spectacular', '--fail-on-warn', file=out.name)          # raises CommandError on any warning

    def test_protected_endpoints_are_documented_as_bearer_token_endpoints(self):
        with tempfile.NamedTemporaryFile(suffix='.yml') as out:
            call_command('spectacular', file=out.name)
            schema = open(out.name).read()
        self.assertIn('bearerAuth:', schema)
        self.assertIn('bearerFormat: JWT', schema)
