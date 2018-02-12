"""Collection of tests for Account management commands."""
from io import StringIO
from django.core.management import call_command
from django.utils.translation import gettext as _
from django.test import TestCase


from ..models import Account


class AddAccountTest(TestCase):
    """Add Account management command test case."""

    def test_command_output(self):
        """Test saving and processing of a test ARN."""
        out = StringIO()
        test_arn = 'arn:aws:iam::123456789012:role/test_role_210987654321'
        test_id = 123456789012

        call_command('add_account', test_arn, stdout=out)
        self.assertIn(_('ARN Info Stored'), out.getvalue())
        account = Account.objects.get(account_id=test_id)
        self.assertEqual(test_id, account.account_id)
        self.assertEqual(test_arn, account.account_arn)
