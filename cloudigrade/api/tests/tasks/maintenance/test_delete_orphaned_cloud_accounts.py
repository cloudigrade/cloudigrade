"""Collection of tests for tasks.maintenance.delete_orphaned_cloud_accounts."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from api import models
from api.clouds.aws import models as aws_models
from api.clouds.azure import models as azure_models
from api.tasks import maintenance
from api.tests import helper as api_helper
from util.exceptions import SourcesAPINotOkStatus
from util.tests import helper as util_helper


class DeleteOrphanedCloudAccountsTest(TestCase):
    """tasks.delete_orphaned_cloud_accounts test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user = util_helper.generate_test_user()

    def generate_accounts(self):
        """Generate several account in good and bad states for testing."""
        # healthy CloudAccounts with their AwsCloudAccount and AzureCloudAccount
        healthy_accounts = [
            api_helper.generate_cloud_account_aws(user=self.user),
            api_helper.generate_cloud_account_azure(user=self.user),
        ]

        # orphaned CloudAccount without its AwsCloudAccount
        account_no_aws = api_helper.generate_cloud_account_aws(user=self.user)
        aws_cloud_account_query = aws_models.AwsCloudAccount.objects.filter(
            id=account_no_aws.content_object.id
        )
        aws_cloud_account_query._raw_delete(aws_cloud_account_query.db)
        account_no_aws = models.CloudAccount.objects.get(id=account_no_aws.id)

        # orphaned CloudAccount without its AzureCloudAccount
        account_no_azure = api_helper.generate_cloud_account_azure(user=self.user)
        azure_cloud_account_query = azure_models.AzureCloudAccount.objects.filter(
            id=account_no_azure.content_object.id
        )
        azure_cloud_account_query._raw_delete(azure_cloud_account_query.db)
        account_no_azure = models.CloudAccount.objects.get(id=account_no_azure.id)

        orphaned_accounts = [account_no_azure, account_no_aws]

        # orphaned AwsCloudAccount without its CloudAccount
        account_aws = api_helper.generate_cloud_account_aws(user=self.user)
        orphaned_aws_cloud_account = account_aws.content_object
        cloud_account_query = models.CloudAccount.objects.filter(id=account_aws.id)
        cloud_account_query._raw_delete(cloud_account_query.db)

        # orphaned CloudAccount without its AzureCloudAccount
        account_azure = api_helper.generate_cloud_account_azure(user=self.user)
        orphaned_azure_cloud_account = account_azure.content_object
        cloud_account_query = models.CloudAccount.objects.filter(id=account_azure.id)
        cloud_account_query._raw_delete(cloud_account_query.db)

        orphaned_content_objects = [
            orphaned_aws_cloud_account,
            orphaned_azure_cloud_account,
        ]

        return healthy_accounts, orphaned_accounts, orphaned_content_objects

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_orphaned_cloud_accounts(self):
        """
        Test identifying and deleting orphaned account without sources.

        We create multiple accounts in healthy and orphaned states that are old and new.
        Expect only the old orphaned accounts should be deleted.
        """
        long_ago = util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        recently = util_helper.utc_dt(2021, 11, 17, 0, 0, 0)

        with util_helper.clouditardis(long_ago):
            # We need to generate in the past so they are old enough to be found.
            (
                old_healthy_accounts,
                old_orphaned_accounts,
                old_orphaned_content_objects,
            ) = self.generate_accounts()

        with util_helper.clouditardis(recently):
            # We need to generate recently so they are too new to be found.
            (
                new_healthy_accounts,
                new_orphaned_accounts,
                new_orphaned_content_objects,
            ) = self.generate_accounts()

        expected_cloud_accounts_before = (
            old_healthy_accounts
            + old_orphaned_accounts
            + new_healthy_accounts
            + new_orphaned_accounts
        )
        expected_cloud_accounts_after = (
            old_healthy_accounts + new_healthy_accounts + new_orphaned_accounts
        )

        self.assertEqual(
            len(expected_cloud_accounts_before), models.CloudAccount.objects.count()
        )

        with util_helper.clouditardis(recently), patch(
            "util.redhatcloud.sources.get_source"
        ) as mock_get_source, self.assertLogs(
            "api.tasks.maintenance", level="INFO"
        ) as logging_watcher:
            mock_get_source.return_value = None
            maintenance.delete_orphaned_cloud_accounts()

        info_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "INFO"
        }
        expected_info_messages = [
            f"Found {len(old_orphaned_accounts)} orphaned CloudAccount instances; "
            f"attempted to delete {len(old_orphaned_accounts)} of them.",
            "Found 2 orphaned CloudAccount instances; attempted to delete 2 of them.",
            "Found 1 orphaned AwsCloudAccount instances to delete",
            "Found 1 orphaned AzureCloudAccount instances to delete",
        ]
        for expected_info_message in expected_info_messages:
            self.assertIn(expected_info_message, info_messages)

        self.assertEqual(
            len(expected_cloud_accounts_after), models.CloudAccount.objects.count()
        )
        self.assertEqual(
            len(expected_cloud_accounts_after),
            models.CloudAccount.objects.filter(
                id__in=[account.id for account in expected_cloud_accounts_after]
            ).count(),
        )
        self.assertEqual(
            len(expected_cloud_accounts_after),
            models.CloudAccount.objects.exclude(
                id__in=[account.id for account in old_orphaned_accounts]
            ).count(),
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_orphaned_cloud_accounts_not_if_source_exists(self):
        """Test identifying but not deleting accounts that still have sources."""
        long_ago = util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        recently = util_helper.utc_dt(2021, 11, 17, 0, 0, 0)

        with util_helper.clouditardis(long_ago):
            # We need to generate in the past so they are old enough to be found.
            healthy_accounts, orphaned_accounts, _ = self.generate_accounts()

        expected_cloud_accounts = healthy_accounts + orphaned_accounts

        self.assertEqual(
            len(expected_cloud_accounts), models.CloudAccount.objects.count()
        )

        dummy_source = {"hello": "world"}  # irrelevant content; needs to be not None
        with util_helper.clouditardis(recently), patch(
            "util.redhatcloud.sources.get_source"
        ) as mock_get_source, self.assertLogs(
            "api.tasks.maintenance", level="INFO"
        ) as logging_watcher:
            mock_get_source.return_value = dummy_source
            maintenance.delete_orphaned_cloud_accounts()

        info_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "INFO"
        }
        self.assertIn(
            f"Found {len(orphaned_accounts)} orphaned CloudAccount instances; "
            f"attempted to delete 0 of them.",
            info_messages,
        )

        expected_error_messages = {
            f"Orphaned account still has a source! Please investigate! "
            f"account {account} has source {dummy_source}"
            for account in orphaned_accounts
        }
        error_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "ERROR"
        }
        self.assertEqual(expected_error_messages, error_messages)

        self.assertEqual(
            len(expected_cloud_accounts), models.CloudAccount.objects.count()
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_orphaned_cloud_accounts_not_if_sources_api_is_down(self):
        """Test identifying but not deleting accounts if sources-api is down."""
        long_ago = util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        recently = util_helper.utc_dt(2021, 11, 17, 0, 0, 0)

        with util_helper.clouditardis(long_ago):
            # We need to generate in the past so they are old enough to be found.
            healthy_accounts, orphaned_accounts, _ = self.generate_accounts()

        expected_cloud_accounts = healthy_accounts + orphaned_accounts

        self.assertEqual(
            len(expected_cloud_accounts), models.CloudAccount.objects.count()
        )

        sources_api_error = SourcesAPINotOkStatus("503 unavailable")
        with util_helper.clouditardis(recently), patch(
            "util.redhatcloud.sources.get_source"
        ) as mock_get_source, self.assertLogs(
            "api.tasks.maintenance", level="INFO"
        ) as logging_watcher:
            mock_get_source.side_effect = sources_api_error
            maintenance.delete_orphaned_cloud_accounts()

        info_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "INFO"
        }
        self.assertIn(
            f"Found {len(orphaned_accounts)} orphaned CloudAccount instances; "
            f"attempted to delete 0 of them.",
            info_messages,
        )

        expected_error_messages = {str(sources_api_error), str(sources_api_error)}
        error_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "ERROR"
        }
        self.assertEqual(expected_error_messages, error_messages)

        expected_warning_messages = {
            f"Unexpected error getting source for {account}: {sources_api_error}"
            for account in orphaned_accounts
        }
        warning_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "WARNING"
        }
        self.assertEqual(expected_warning_messages, warning_messages)

        self.assertEqual(
            len(expected_cloud_accounts), models.CloudAccount.objects.count()
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT=False)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_orphaned_cloud_accounts_if_sources_data_management_disabled(self):
        """Test skipping task if sources api data management is disabled."""
        long_ago = util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        recently = util_helper.utc_dt(2021, 11, 17, 0, 0, 0)

        with util_helper.clouditardis(long_ago):
            # We need to generate in the past so they are old enough to be found.
            healthy_accounts, orphaned_accounts, _ = self.generate_accounts()

        expected_cloud_accounts = healthy_accounts + orphaned_accounts

        self.assertEqual(
            len(expected_cloud_accounts), models.CloudAccount.objects.count()
        )

        with util_helper.clouditardis(recently), patch(
            "util.redhatcloud.sources.get_source"
        ) as mock_get_source, self.assertLogs(
            "api.tasks.maintenance", level="INFO"
        ) as logging_watcher:
            mock_get_source.return_value = None
            maintenance.delete_orphaned_cloud_accounts()

        info_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "INFO"
        }
        self.assertIn(
            "Skipping delete_orphaned_cloud_accounts because "
            "settings.SOURCES_ENABLE_DATA_MANAGEMENT is not enabled.",
            info_messages,
        )

        self.assertEqual(
            len(expected_cloud_accounts), models.CloudAccount.objects.count()
        )
        self.assertEqual(
            len(expected_cloud_accounts),
            models.CloudAccount.objects.filter(
                id__in=[account.id for account in expected_cloud_accounts]
            ).count(),
        )
