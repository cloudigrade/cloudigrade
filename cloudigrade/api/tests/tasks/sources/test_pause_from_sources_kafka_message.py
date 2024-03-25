"""Collection of tests for tasks.pause_from_sources_kafka_message."""

from unittest.mock import patch

import faker
from django.test import TestCase

from api.models import CloudAccount
from api.tasks import sources
from api.tests import helper as api_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class PauseFromSourcesKafkaMessageTest(TestCase):
    """Celery task 'pause_from_sources_kafka_message' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.cloud_account = api_helper.generate_cloud_account()
        self.account_number = self.cloud_account.user.account_number
        self.application_id = self.cloud_account.platform_application_id

    def test_pause_from_sources_kafka_message_success(self):
        """Test pause_from_sources_kafka_message happy path."""
        message, headers = util_helper.generate_application_event_message_value(
            "pause", self.application_id, self.account_number
        )
        self.assertFalse(self.cloud_account.platform_application_is_paused)
        with patch.object(CloudAccount, "disable") as mock_disable:
            sources.pause_from_sources_kafka_message(message, headers)
        mock_disable.assert_called_once_with(notify_sources=False)
        self.cloud_account.refresh_from_db()
        self.assertTrue(self.cloud_account.platform_application_is_paused)

    def test_pause_from_sources_kafka_message_errors_missing_headers(self):
        """Test pause_from_sources_kafka_message when headers are missing."""
        self.assertFalse(self.cloud_account.platform_application_is_paused)
        with patch.object(CloudAccount, "disable") as mock_disable, self.assertLogs(
            "api.tasks.sources", level="ERROR"
        ) as log_context:
            sources.pause_from_sources_kafka_message({}, [])
        mock_disable.assert_not_called()
        self.cloud_account.refresh_from_db()
        self.assertFalse(self.cloud_account.platform_application_is_paused)
        self.assertEqual(len(log_context.records), 1)
        self.assertEqual(log_context.records[0].levelname, "ERROR")
        self.assertIn("Incorrect message details", log_context.records[0].message)

    def test_pause_from_sources_kafka_message_errors_unknown_cloudaccount(self):
        """Test pause_from_sources_kafka_message when no CloudAccount is found."""
        message, headers = util_helper.generate_application_event_message_value(
            "pause", _faker.pyint(), self.account_number
        )
        self.assertFalse(self.cloud_account.platform_application_is_paused)
        with patch.object(CloudAccount, "disable") as mock_disable, self.assertLogs(
            "api.tasks.sources", level="INFO"
        ) as log_context:
            sources.pause_from_sources_kafka_message(message, headers)
        mock_disable.assert_not_called()
        self.cloud_account.refresh_from_db()
        self.assertFalse(self.cloud_account.platform_application_is_paused)
        self.assertEqual(len(log_context.records), 1)
        self.assertEqual(log_context.records[0].levelname, "INFO")
        self.assertIn("does not exist", log_context.records[0].message)
