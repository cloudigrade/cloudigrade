from io import StringIO
from django.core.management import call_command
from django.test import TestCase


class AddAccountTest(TestCase):
    def test_command_output(self):
        out = StringIO()
        call_command('add_account', stdout=out)
        self.assertIn('AWS Account Added... probably', out.getvalue())
