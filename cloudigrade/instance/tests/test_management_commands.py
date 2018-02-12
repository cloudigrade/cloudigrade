"""Collection of tests for Instance management commands."""
import uuid
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils.translation import gettext as _

from instance.management.commands import check_instances


class CheckInstancesTest(TestCase):
    """Assert behaviors for the ``check_instances`` management command."""

    def test_get_running_instances(self):
        """Assert we get expected instances when using mock boto calls."""
        mock_arn = 'arn:aws:iam::123456789012:role/test_role_210987654321'
        mock_regions = [f'region-{uuid.uuid4()}']
        mock_credentials = {
            'AccessKeyId': str(uuid.uuid4()),
            'SecretAccessKey': str(uuid.uuid4()),
            'SessionToken': str(uuid.uuid4()),
        }
        mock_instance_id = str(uuid.uuid4())
        mock_described = {
            'Reservations': [
                {
                    'Instances': [
                        {
                            'InstanceId': mock_instance_id,
                        },
                    ],
                },
            ],
        }
        expected_found = {
            mock_regions[0]: [mock_instance_id]
        }

        with mock.patch.object(check_instances, 'aws') as mock_aws, \
                mock.patch.object(check_instances, 'boto3') as mock_boto3:
            mock_aws.get_regions.return_value = mock_regions
            mock_aws.get_credentials_for_arn.return_value = mock_credentials
            mock_client = mock_boto3.Session.return_value.client.return_value
            mock_client.describe_instances.return_value = mock_described

            actual_found = check_instances.get_running_instances(mock_arn)

        self.assertDictEqual(expected_found, actual_found)

    def test_command_output(self):
        """Assert expected command output for ``check_instances``."""
        mock_arn = 'arn:aws:iam::123456789012:role/test_role_210987654321'
        mock_instances = {
            f'region-{uuid.uuid4()}': [str(uuid.uuid4())],
        }
        expected_stdout = _(f'Instances found include: {mock_instances}')
        captured_stdout = StringIO()

        with mock.patch.object(check_instances, 'get_running_instances') as \
                mock_get_running_instances:
            mock_get_running_instances.return_value = mock_instances
            call_command('check_instances', mock_arn, stdout=captured_stdout)

        self.assertIn(expected_stdout, captured_stdout.getvalue())
