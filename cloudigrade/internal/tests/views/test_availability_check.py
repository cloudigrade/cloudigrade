"""Collection of tests for Availability Check."""
from unittest.mock import patch

import faker
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.tasks import enable_account
from api.tests import helper as api_helper
from internal.views import availability_check
from util.tests import helper as util_helper

_faker = faker.Faker()


class AvailabilityCheckViewTest(TestCase):
    """Availability Check View test case."""

    def setUp(self):
        """Set up a bunch shared test data."""
        self.user = util_helper.generate_test_user()

        source_id = _faker.pyint()
        self.account = api_helper.generate_cloud_account(
            user=self.user,
            platform_authentication_id=_faker.pyint(),
            platform_application_id=_faker.pyint(),
            platform_source_id=source_id,
            is_enabled=False,
        )
        self.account2 = api_helper.generate_cloud_account(
            user=self.user,
            platform_authentication_id=_faker.pyint(),
            platform_application_id=_faker.pyint(),
            platform_source_id=source_id,
            is_enabled=False,
        )
        self.factory = APIRequestFactory()

    @patch("internal.views.enable_account")
    def test_availability_check_success(self, mock_enable):
        """Test happy path success for availability_check."""
        request = self.factory.post(
            "/availability_check/", data={"source_id": self.account.platform_source_id}
        )
        force_authenticate(request, user=self.user)

        response = availability_check(request)
        self.assertEqual(response.status_code, 204)

        mock_enable.delay.assert_called()

    @patch("api.tasks.notify_application_availability_task")
    def test_availability_check_task(self, mock_notify_sources):
        """Test the task that is called by the availability_check_api."""
        with patch("api.clouds.aws.util.verify_permissions") as mock_verify_permissions:
            mock_verify_permissions.return_value = True
            enable_account(self.account.id)
            enable_account(self.account2.id)

        self.account.refresh_from_db()
        self.assertTrue(self.account.is_enabled)
        self.account2.refresh_from_db()
        self.assertTrue(self.account2.is_enabled)
        mock_notify_sources.delay.assert_called()

    def test_availability_check_task_bad_clount_id(self):
        """Test that task properly handles deleted accounts."""
        with self.assertLogs("api.tasks", level="WARNING") as logs:
            enable_account(123456)

        self.assertIn(
            "Cloud Account with ID 123456 does not exist. "
            "No cloud account to enable, exiting.",
            logs.output[0],
        )

    def test_availability_fails_no_source_id(self):
        """Test that availability_check returns 400 if no source_id is passed."""
        request = self.factory.post("/availability_check/")
        force_authenticate(request, user=self.user)

        response = availability_check(request)
        self.assertEqual(response.status_code, 400)
