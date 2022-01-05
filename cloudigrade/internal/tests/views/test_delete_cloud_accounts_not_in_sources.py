"""Collection of tests for Deleting Cloud Accounts Not In Sources."""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from internal import views
from util.tests import helper as util_helper


class DeleteCloudAccountsNotInSourcesTest(TestCase):
    """Delete Cloud Accounts Not In Sources test case."""

    def setUp(self):
        """Set up a bunch shared test data."""
        self.user = util_helper.generate_test_user()
        self.factory = APIRequestFactory()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.delete_cloud_accounts_not_in_sources")
    def test_delete_cloud_accounts_not_in_sources(self, mock_delete_cloud_accounts):
        """Test internal delete_cloud_accounts_not_in_sources action."""
        request = self.factory.post("/delete_cloud_accounts_not_in_sources/", data={})
        force_authenticate(request, user=self.user)

        response = views.delete_cloud_accounts_not_in_sources(request)
        self.assertEqual(response.status_code, 202)

        mock_delete_cloud_accounts.apply_async.assert_called()
