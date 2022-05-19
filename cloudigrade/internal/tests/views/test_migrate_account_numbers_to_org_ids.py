"""Collection of tests for Migrating Account Numbers to Org Ids."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from internal import views
from util.tests import helper as util_helper


class MigrateAccountNumbersToOrgIdsTest(TestCase):
    """Migrate Account Numbers To Org Ids test case."""

    def setUp(self):
        """Set up a bunch shared test data."""
        self.user = util_helper.generate_test_user()
        self.factory = APIRequestFactory()

    @patch("api.tasks.migrate_account_numbers_to_org_ids")
    def test_migrate_account_numbers_to_org_ids(self, mock_migrate_account_numbers):
        """Test internal migrate_account_numbers_to_org_ids action."""
        request = self.factory.post("/migrate_account_numbers_to_org_ids/", data={})
        force_authenticate(request, user=self.user)

        response = views.migrate_account_numbers_to_org_ids(request)
        self.assertEqual(response.status_code, 202)

        mock_migrate_account_numbers.apply_async.assert_called()
