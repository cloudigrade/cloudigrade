"""Collection of tests for Account management commands."""
import uuid
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils.translation import gettext as _

from account.management.commands.add_account import aws
from account.models import Account
from util.tests import helper


class AddAccountTest(TestCase):
    """Add Account management command test case."""

    def test_command_output(self):
        """Test saving and processing of a test ARN."""
        out = StringIO()

        mock_account_id = helper.generate_dummy_aws_account_id()
        mock_arn = helper.generate_dummy_arn(mock_account_id)
        mock_instances = {
            f'region-{uuid.uuid4()}': [str(uuid.uuid4())],
        }

        expected_instances = _(f'Instances found include: {mock_instances}')
        expected_account = _('ARN Info Stored')

        with patch.object(aws, 'get_running_instances') as mock_get_running:
            mock_get_running.return_value = mock_instances
            call_command('add_account', mock_arn, stdout=out)

        actual_stdout = out.getvalue()
        self.assertIn(expected_account, actual_stdout)
        self.assertIn(expected_instances, actual_stdout)

        account = Account.objects.get(account_id=mock_account_id)
        self.assertEqual(mock_account_id, account.account_id)
        self.assertEqual(mock_arn, account.account_arn)
