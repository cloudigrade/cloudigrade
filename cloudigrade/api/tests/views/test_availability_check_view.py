"""Collection of tests for Availability Check."""
from unittest.mock import patch

import faker
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.tests import helper as api_helper
from api.views import availability_check
from util.tests import helper as util_helper


_faker = faker.Faker()


class AvailabilityCheckViewTest(TestCase):
    """Availability Check View test case."""

    def setUp(self):
        """Set up a bunch shared test data."""
        self.user = util_helper.generate_test_user()

        source_id = _faker.pyint()
        self.account = api_helper.generate_aws_account(
            user=self.user,
            platform_authentication_id=_faker.pyint(),
            platform_application_id=_faker.pyint(),
            platform_endpoint_id=_faker.pyint(),
            platform_source_id=source_id,
            is_enabled=False,
        )
        self.account2 = api_helper.generate_aws_account(
            user=self.user,
            platform_authentication_id=_faker.pyint(),
            platform_application_id=_faker.pyint(),
            platform_endpoint_id=_faker.pyint(),
            platform_source_id=source_id,
            is_enabled=False,
        )
        self.factory = APIRequestFactory()

    @patch("api.models.notify_sources_application_availability")
    def test_availability_check_success(self, mock_sources_notify):
        """Test happy path success for availability_check."""
        request = self.factory.post(
            "/availability_check/", data={"source_id": self.account.platform_source_id}
        )
        force_authenticate(request, user=self.user)

        with patch("api.clouds.aws.util.verify_permissions") as mock_verify_permissions:
            mock_verify_permissions.return_value = True
            response = availability_check(request)
            self.assertEqual(response.status_code, 204)

        self.account.refresh_from_db()
        self.assertTrue(self.account.is_enabled)
        self.account2.refresh_from_db()
        self.assertTrue(self.account2.is_enabled)
        mock_sources_notify.assert_called()

    def test_availability_fails_no_source_id(self):
        """Test that availability_check returns 400 if no source_id is passed."""
        request = self.factory.post("/availability_check/")
        force_authenticate(request, user=self.user)

        response = availability_check(request)
        self.assertEqual(response.status_code, 400)
