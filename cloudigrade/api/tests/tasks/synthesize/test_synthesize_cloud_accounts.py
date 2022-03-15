"""Collection of tests for api.tasks.synthesize.synthesize_cloud_accounts."""

from django.test import TestCase

from api import AWS_PROVIDER_STRING, CLOUD_PROVIDERS, models
from api.tasks import synthesize
from api.tests.tasks.synthesize import create_synthetic_data_request_without_post_save


class SynthesizeCloudAccountsTest(TestCase):
    """api.tasks.synthesize_cloud_accounts test case."""

    def test_synthesize_cloud_accounts(self):
        """
        Test happy path to create CloudAccounts for the SyntheticDataRequest.

        We expect requests for all CLOUD_PROVIDERS to have non-zero counts of their
        respective CloudAccount types to be created successfully.
        """
        expected_total_account_count = 0
        for cloud_type in CLOUD_PROVIDERS:
            request = create_synthetic_data_request_without_post_save(
                cloud_type=cloud_type
            )
            expected_total_account_count += request.account_count
            response = synthesize.synthesize_cloud_accounts(request.id)
            self.assertEqual(response, request.id)
            request.refresh_from_db()
            self.assertGreater(request.account_count, 0)
            self.assertEqual(
                request.account_count,
                models.CloudAccount.objects.filter(user=request.user).count(),
            )
            for cloud_account in models.CloudAccount.objects.filter(user=request.user):
                self.assertTrue(cloud_account.is_synthetic)
                self.assertEqual(cloud_account.cloud_type, request.cloud_type)
        self.assertEqual(
            expected_total_account_count, models.CloudAccount.objects.count()
        )

    def test_synthesize_cloud_accounts_but_no_user(self):
        """Test early return if the SyntheticDataRequest has no User."""
        request = create_synthetic_data_request_without_post_save(
            cloud_type=AWS_PROVIDER_STRING, synthesize_user=False
        )
        response = synthesize.synthesize_cloud_accounts(request.id)
        self.assertIsNone(response)
        self.assertFalse(models.CloudAccount.objects.exists())

    def test_synthesize_cloud_accounts_but_request_id_not_found(self):
        """Test early return if the SyntheticDataRequest does not exist."""
        self.assertFalse(models.SyntheticDataRequest.objects.exists())
        response = synthesize.synthesize_cloud_accounts(1)
        self.assertIsNone(response)
        self.assertFalse(models.CloudAccount.objects.exists())
