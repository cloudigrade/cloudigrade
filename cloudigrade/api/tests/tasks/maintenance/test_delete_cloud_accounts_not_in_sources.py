"""Collection of tests for tasks.maintenance.delete_cloud_accounts_not_in_sources."""
from unittest.mock import patch

from django.test import TestCase, override_settings

from api import models
from api.tasks import maintenance
from api.tests import helper as api_helper
from util.exceptions import SourcesAPINotOkStatus
from util.tests import helper as util_helper


class DeleteCloudAccountsNotInSourcesTest(TestCase):
    """tasks.delete_cloud_accounts_not_in_sources test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user = util_helper.generate_test_user()

    def generate_accounts(self):
        """Generate several healthy accounts for testing."""
        # healthy CloudAccounts with their AwsCloudAccount and AzureCloudAccount
        healthy_accounts = [
            api_helper.generate_cloud_account_aws(user=self.user),
            api_helper.generate_cloud_account_azure(user=self.user),
        ]

        return healthy_accounts

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_cloud_accounts_not_in_sources(self):
        """
        Test deleting old healthy account not in sources.

        We create multiple old and new healthy accounts that are not
        in sources. Expect only the old healthy accounts to be deleted.
        """
        long_ago = util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        recently = util_helper.utc_dt(2021, 11, 17, 0, 0, 0)

        with util_helper.clouditardis(long_ago):
            # We need to generate in the past so they are old enough to be considered.
            old_healthy_accounts_not_in_sources = self.generate_accounts()

        with util_helper.clouditardis(recently):
            # We need to generate recent so they are too new to be considered.
            new_healthy_accounts_not_in_sources = (
                self.generate_accounts() + self.generate_accounts()
            )

        expected_cloud_accounts_before = (
            old_healthy_accounts_not_in_sources + new_healthy_accounts_not_in_sources
        )
        expected_cloud_accounts_after = new_healthy_accounts_not_in_sources

        self.assertEqual(
            len(expected_cloud_accounts_before), models.CloudAccount.objects.count()
        )

        with util_helper.clouditardis(recently), patch(
            "util.redhatcloud.sources.get_source"
        ) as mock_get_source, self.assertLogs(
            "api.tasks.maintenance", level="INFO"
        ) as logging_watcher:
            mock_get_source.return_value = None
            maintenance.delete_cloud_accounts_not_in_sources()

        info_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "INFO"
        }

        expected_info_messages = [
            f"Searching {len(expected_cloud_accounts_before)}"
            " CloudAccount instances potentially not in sources.",
            f"Checked {len(old_healthy_accounts_not_in_sources)}"
            " CloudAccount instances potentially not in sources.",
            f"Found {len(old_healthy_accounts_not_in_sources)}"
            " CloudAccount instances not in sources.",
        ] + [
            f"Deleting CloudAccount with ID {account.id}"
            for account in old_healthy_accounts_not_in_sources
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
                id__in=[account.id for account in old_healthy_accounts_not_in_sources]
            ).count(),
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_cloud_accounts_not_in_sources_if_source_exists(self):
        """Test not deleting accounts that still have sources."""
        long_ago = util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        recently = util_helper.utc_dt(2021, 11, 17, 0, 0, 0)

        with util_helper.clouditardis(long_ago):
            # We need to generate in the past so they are old enough to be considered.
            old_healthy_accounts_not_in_sources = self.generate_accounts()

        with util_helper.clouditardis(recently):
            # We need to generate recent so they are too new to be considered.
            new_healthy_accounts_not_in_sources = (
                self.generate_accounts() + self.generate_accounts()
            )

        expected_cloud_accounts_before = expected_cloud_accounts_after = (
            old_healthy_accounts_not_in_sources + new_healthy_accounts_not_in_sources
        )

        self.assertEqual(
            len(expected_cloud_accounts_before), models.CloudAccount.objects.count()
        )

        dummy_source = {"availability_status": "available"}
        with util_helper.clouditardis(recently), patch(
            "util.redhatcloud.sources.get_source"
        ) as mock_get_source, self.assertLogs(
            "api.tasks.maintenance", level="INFO"
        ) as logging_watcher:
            mock_get_source.return_value = dummy_source
            maintenance.delete_cloud_accounts_not_in_sources()

        info_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "INFO"
        }

        expected_info_messages = [
            f"Searching {len(expected_cloud_accounts_before)}"
            " CloudAccount instances potentially not in sources.",
            f"Checked {len(old_healthy_accounts_not_in_sources)}"
            " CloudAccount instances potentially not in sources.",
            "Found 0 CloudAccount instances not in sources.",
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

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_cloud_accounts_not_in_sources_not_if_sources_api_is_down(self):
        """Test identifying but not deleting accounts if sources-api is down."""
        long_ago = util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        recently = util_helper.utc_dt(2021, 11, 17, 0, 0, 0)

        with util_helper.clouditardis(long_ago):
            # We need to generate in the past so they are old enough to be found.
            old_healthy_accounts_not_in_sources = self.generate_accounts()

        with util_helper.clouditardis(recently):
            # We need to generate recent so they are too new to be considered.
            new_healthy_accounts_not_in_sources = (
                self.generate_accounts() + self.generate_accounts()
            )

        expected_cloud_accounts_before = expected_cloud_accounts_after = (
            old_healthy_accounts_not_in_sources + new_healthy_accounts_not_in_sources
        )

        self.assertEqual(
            len(expected_cloud_accounts_before), models.CloudAccount.objects.count()
        )

        sources_api_error = SourcesAPINotOkStatus("503 unavailable")
        with util_helper.clouditardis(recently), patch(
            "util.redhatcloud.sources.get_source"
        ) as mock_get_source, self.assertLogs(
            "api.tasks.maintenance", level="INFO"
        ) as logging_watcher:
            mock_get_source.side_effect = sources_api_error
            maintenance.delete_cloud_accounts_not_in_sources()

        info_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "INFO"
        }

        expected_info_messages = [
            f"Searching {len(expected_cloud_accounts_before)}"
            " CloudAccount instances potentially not in sources.",
            f"Checked {len(old_healthy_accounts_not_in_sources)}"
            " CloudAccount instances potentially not in sources.",
            "Found 0 CloudAccount instances not in sources.",
        ]
        for expected_info_message in expected_info_messages:
            self.assertIn(expected_info_message, info_messages)

        expected_error_messages = {str(sources_api_error), str(sources_api_error)}
        error_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "ERROR"
        }
        self.assertEqual(expected_error_messages, error_messages)

        expected_warning_messages = {
            f"Unexpected error getting source for {account}: {sources_api_error}"
            for account in old_healthy_accounts_not_in_sources
        }
        warning_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "WARNING"
        }
        self.assertEqual(expected_warning_messages, warning_messages)

        self.assertEqual(
            len(expected_cloud_accounts_after), models.CloudAccount.objects.count()
        )
