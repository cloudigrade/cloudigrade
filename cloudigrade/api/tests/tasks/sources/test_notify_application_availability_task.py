"""Collection of tests for ``api.tasks.notify_application_availability_task``."""

from unittest.mock import patch

import faker
from django.test import TestCase

from api.tasks.sources import notify_application_availability_task
from util.exceptions import KafkaProducerException

_faker = faker.Faker()


class NotifyApplicationAvailabilityTaskTest(TestCase):
    """Celery task 'notify_application_availability_task' test cases."""

    def setUp(self):
        """Set up shared variables."""
        self.account_number = str(_faker.pyint())
        self.org_id = None
        self.application_id = _faker.pyint()

    @patch("util.redhatcloud.sources.notify_application_availability")
    def test_notify_application_availability_task_success(self, mock_notify_sources):
        """Assert notify_application_availability with available message success."""
        notify_application_availability_task(
            self.account_number, self.org_id, self.application_id, "available", ""
        )
        mock_notify_sources.assert_called_with(
            self.account_number, self.org_id, self.application_id, "available", ""
        )

    @patch("util.redhatcloud.sources.notify_application_availability")
    def test_notify_application_availability_task_with_error_success(
        self, mock_notify_sources
    ):
        """Assert notify_application_availability with unavailable message success."""
        notify_application_availability_task(
            self.account_number,
            self.org_id,
            self.application_id,
            "unavailable",
            "bad_error",
        )
        mock_notify_sources.assert_called_with(
            self.account_number,
            self.org_id,
            self.application_id,
            "unavailable",
            "bad_error",
        )

    @patch("util.redhatcloud.sources.notify_application_availability")
    def test_notify_application_availability_task_with_exception(
        self, mock_notify_sources
    ):
        """Assert notify_application_availability with available message exception."""
        mock_notify_sources.side_effect = KafkaProducerException("network error")
        with self.assertRaises(KafkaProducerException):
            notify_application_availability_task(
                self.account_number, self.org_id, self.application_id, "available", ""
            )
        mock_notify_sources.assert_called_with(
            self.account_number, self.org_id, self.application_id, "available", ""
        )
