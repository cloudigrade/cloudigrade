"""Collection of tests for the 'create_runs' management command."""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class CreatePskTest(TestCase):
    """Management command 'create_psk' test case."""

    def setUp(self):
        """Set up test data."""
        self.stdout = StringIO()
        self.stderr = StringIO()
        self.psk_pattern = "[a-z0-9]{8}-[a-z0-9]{8}-[a-z0-9]{8}-[a-z0-9]{8}"

    def test_create_psk_without_service_name(self):
        """Expects to fail without a service name specified."""
        with self.assertRaises(CommandError) as e:
            call_command("create_psk", stdout=self.stdout, stderr=self.stderr)
        self.assertIn(
            "the following arguments are required: svc_name", e.exception.args[0]
        )

    def test_create_psk(self):
        """Create a PSK for a service."""
        svc_name = "sample-service"
        call_command("create_psk", svc_name, stdout=self.stdout, stderr=self.stderr)
        command_output = self.stdout.getvalue()
        expected_pattern = (
            r"Service Name:\s+{svc_name}\nNew Cloudigrade PSK:\s+{psk_pattern}\n"
        ).format(
            svc_name=svc_name,
            psk_pattern=self.psk_pattern,
        )
        self.assertRegex(command_output, expected_pattern)

    def test_create_psk_and_add_to_psks(self):
        """Create a PSK for a service and add it to the list of PSKs."""
        svc_name = "a-new-service"
        current_psks = "current-service:09ABCDEF"
        cmd_args = ["create_psk", "--psks", current_psks, svc_name]
        call_command(*cmd_args, stdout=self.stdout, stderr=self.stderr)
        command_output = self.stdout.getvalue()
        expected_pattern = (
            r"Service Name:\s+{svc_name}\n"
            r"New Cloudigrade PSK:\s+{psk_pattern}\n"
            r"Current Cloudigrade PSKs:\s+{current_psks}\n"
            r"Updated Cloudigrade PSKs:\s+{svc_name}:{psk_pattern},{current_psks}\n"
        ).format(
            svc_name=svc_name,
            psk_pattern=self.psk_pattern,
            current_psks=current_psks,
        )
        self.assertRegex(command_output, expected_pattern)
