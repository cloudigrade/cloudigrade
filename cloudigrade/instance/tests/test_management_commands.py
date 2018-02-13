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

    def test_command_output(self):
        """Assert expected command output for ``check_instances``."""
        mock_arn = 'arn:aws:iam::123456789012:role/test_role_210987654321'
        mock_instances = {
            f'region-{uuid.uuid4()}': [str(uuid.uuid4())],
        }
        expected_stdout = _(f'Instances found include: {mock_instances}')
        captured_stdout = StringIO()

        with mock.patch.object(check_instances, 'aws') as mock_aws:
            mock_aws.get_running_instances.return_value = mock_instances
            call_command('check_instances', mock_arn, stdout=captured_stdout)

        self.assertIn(expected_stdout, captured_stdout.getvalue())
