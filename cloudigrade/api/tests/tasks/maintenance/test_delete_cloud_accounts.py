"""Collection of tests for tasks.maintenance._delete_cloud_accounts helper function."""

from django.test import TestCase, override_settings

from api import models
from api.clouds.aws import models as aws_models
from api.tasks import maintenance
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class DeleteCloudAccountsTest(TestCase):
    """tasks._delete_cloud_accounts test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user = util_helper.generate_test_user()

        self.account_aws_1 = api_helper.generate_cloud_account_aws(user=self.user)
        self.account_aws_2 = api_helper.generate_cloud_account_aws(user=self.user)
        self.account_azure_1 = api_helper.generate_cloud_account_azure(user=self.user)
        self.account_azure_2 = api_helper.generate_cloud_account_azure(user=self.user)

    def assertObjectCountsBeforeDelete(self):
        """Sanity-check expected object counts before deleting."""
        self.assertEqual(models.CloudAccount.objects.count(), 4)

    def assertObjectCountsAfterDelete(self, accounts_deleted=1):
        """Sanity-check expected object counts before deleting."""
        self.assertEqual(models.CloudAccount.objects.count(), 4 - accounts_deleted)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_cloud_accounts_single_aws(self):
        """
        Test deleting one AWS account should not affect other accounts.

        The image that was used by instances in both AWS accounts should still exist.
        """
        self.assertObjectCountsBeforeDelete()

        maintenance.delete_cloud_account(self.account_aws_1.id)

        self.assertObjectCountsAfterDelete()
        # The deleted account should not exist, but the other should be okay.
        with self.assertRaises(models.CloudAccount.DoesNotExist):
            self.account_aws_1.refresh_from_db()
        self.account_aws_2.refresh_from_db()
        self.account_azure_1.refresh_from_db()
        self.account_azure_2.refresh_from_db()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_cloud_accounts_single_azure(self):
        """
        Test deleting one Azure account should not affect other accounts.

        The image that was used by instances in both Azure accounts should still exist.
        """
        self.assertObjectCountsBeforeDelete()

        maintenance.delete_cloud_account(self.account_azure_1.id)

        self.assertObjectCountsAfterDelete()
        # The deleted account should not exist, but the other should be okay.
        with self.assertRaises(models.CloudAccount.DoesNotExist):
            self.account_azure_1.refresh_from_db()
        self.account_azure_2.refresh_from_db()
        self.account_aws_1.refresh_from_db()
        self.account_aws_2.refresh_from_db()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_cloud_accounts_both_aws(self):
        """Test deleting both AWS accounts also deletes the shared image."""
        self.assertObjectCountsBeforeDelete()

        maintenance.delete_cloud_account(self.account_aws_1.id)
        maintenance.delete_cloud_account(self.account_aws_2.id)

        self.assertObjectCountsAfterDelete(accounts_deleted=2)
        with self.assertRaises(models.CloudAccount.DoesNotExist):
            self.account_aws_1.refresh_from_db()
        with self.assertRaises(models.CloudAccount.DoesNotExist):
            self.account_aws_2.refresh_from_db()
        self.account_azure_1.refresh_from_db()
        self.account_azure_2.refresh_from_db()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_when_missing_cloud_account_content_object(self):
        """Test partial delete when cloud_account.content_object is None."""
        self.assertObjectCountsBeforeDelete()

        # Delete only the related AwsCloudAccount to simulate weird conditions.
        # It's unclear how that could happen unless we have a hidden race condition
        # related to the delete process while processing multiple messages in parallel.
        aws_cloud_accounts = aws_models.AwsCloudAccount.objects.filter(
            id=self.account_aws_1.object_id
        )
        aws_cloud_accounts._raw_delete(aws_cloud_accounts.db)

        # verify the related CloudAccount is still present after the raw_delete above
        self.account_aws_1.refresh_from_db()

        with self.assertLogs(
            "api.tasks.maintenance", level="INFO"
        ) as logs_maintenance, self.assertLogs(
            "api.models", level="INFO"
        ) as logs_models:
            maintenance.delete_cloud_account(self.account_aws_1.id)

        self.assertObjectCountsAfterDelete()
        maintenance_infos = [
            r.getMessage() for r in logs_maintenance.records if r.levelname == "INFO"
        ]
        maintenance_errors = [
            r.getMessage() for r in logs_maintenance.records if r.levelname == "ERROR"
        ]
        model_errors = [
            r.getMessage() for r in logs_models.records if r.levelname == "ERROR"
        ]
        self.assertEqual(len(maintenance_infos), 1)
        self.assertEqual(len(maintenance_errors), 1)
        self.assertEqual(len(model_errors), 1)
        self.assertIn("Deleting CloudAccount with ID", maintenance_infos[0])
        self.assertIn("cloud_account.content_object is None", maintenance_errors[0])
        self.assertIn("content_object is missing", model_errors[0])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_when_missing_multiple_related_objects(self):
        """Test partial delete when multiple related content_objects are None."""
        self.assertObjectCountsBeforeDelete()

        # Delete only the related AwsCloudAccount to simulate weird conditions.
        # It's unclear how that could happen unless we have a hidden race condition
        # related to the delete process while processing multiple messages in parallel.
        aws_cloud_accounts = aws_models.AwsCloudAccount.objects.filter(
            id=self.account_aws_1.object_id
        )
        aws_cloud_accounts._raw_delete(aws_cloud_accounts.db)

        with self.assertLogs("api.tasks.maintenance", level="INFO") as logs_maintenance:
            maintenance.delete_cloud_account(self.account_aws_1.id)

        self.assertObjectCountsAfterDelete()
        maintenance_infos = [
            r.getMessage() for r in logs_maintenance.records if r.levelname == "INFO"
        ]
        maintenance_errors = [
            r.getMessage() for r in logs_maintenance.records if r.levelname == "ERROR"
        ]
        self.assertEqual(len(maintenance_infos), 1)
        self.assertEqual(len(maintenance_errors), 1)
        self.assertIn("Deleting CloudAccount with ID", maintenance_infos[0])
        self.assertIn("cloud_account.content_object is None", maintenance_errors[0])
