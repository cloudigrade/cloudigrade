"""Collection of tests for Account management commands."""
import uuid
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils.translation import gettext as _

from account.management.commands.add_account import aws
from account.models import Account, Instance, InstanceEvent
from util.tests import helper


class AddAccountTest(TestCase):
    """Add Account management command test case."""

    def test_command_output_account_verified(self):
        """Test saving and processing of a test ARN."""
        out = StringIO()

        mock_account_id = helper.generate_dummy_aws_account_id()
        mock_arn = helper.generate_dummy_arn(mock_account_id)
        mock_region = f'region-{uuid.uuid4()}'
        mock_instances = {mock_region: [
            helper.generate_dummy_describe_instance(
                state=aws.InstanceState.running
            ),
            helper.generate_dummy_describe_instance(
                state=aws.InstanceState.stopping
            )
        ]}

        expected_out = _('ARN Info Stored')

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws, 'get_running_instances') as mock_get_running:
            mock_verify.return_value = True
            mock_get_running.return_value = mock_instances
            call_command('add_account', mock_arn, stdout=out)

        actual_stdout = out.getvalue()
        self.assertIn(expected_out, actual_stdout)

        account = Account.objects.get(account_id=mock_account_id)
        self.assertEqual(mock_account_id, account.account_id)
        self.assertEqual(mock_arn, account.account_arn)

        instances = Instance.objects.filter(account=account).all()
        self.assertEqual(len(mock_instances[mock_region]), len(instances))
        for region, mock_instances_list in mock_instances.items():
            for mock_instance in mock_instances_list:
                instance_id = mock_instance['InstanceId']
                instance = Instance.objects.get(ec2_instance_id=instance_id)
                self.assertIsInstance(instance, Instance)
                self.assertEqual(region, instance.region)
                event = InstanceEvent.objects.get(instance=instance)
                self.assertIsInstance(event, InstanceEvent)
                self.assertEqual(InstanceEvent.TYPE.power_on, event.event_type)

    def test_command_output_account_not_verified(self):
        """Test that an account is not saved if verification fails."""
        out = StringIO()

        mock_account_id = helper.generate_dummy_aws_account_id()
        mock_arn = helper.generate_dummy_arn(mock_account_id)

        expected_stdout = _('Account verification failed. ARN Info Not Stored')

        with patch.object(aws, 'verify_account_access') as mock_verify:
            mock_verify.return_value = False
            call_command('add_account', mock_arn, stdout=out)

        actual_stdout = out.getvalue()
        self.assertIn(expected_stdout, actual_stdout)

        self.assertFalse(Account.objects.filter(account_id=mock_account_id)
                         .exists())
