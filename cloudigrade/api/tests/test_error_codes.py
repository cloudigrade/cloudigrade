"""Collection of tests targeting cloudigrade error codes."""
import logging
from unittest.mock import patch

import faker
from django.test import TestCase

from api import error_codes


_faker = faker.Faker()


class ErrorCodeTestCase(TestCase):
    """Test cloudigrade error codes work as expected."""

    def setUp(self):
        """Set up data for tests."""
        self.error_code = _faker.pyint()
        self.custom_error = error_codes.CloudigradeError(
            self.error_code,
            "Longer internal message %(var1)s, %(var2)s",
            "Message including %(error_code)s",
        )

    def test_get_message(self):
        """Test that get_message returns expected results."""
        message = self.custom_error.get_message()
        self.assertEqual("Message including {}".format(self.error_code), message)

    def test_log_internal_message(self):
        """Test that log internal message logs a warning."""
        logger = logging.getLogger(__name__)
        with self.assertLogs(logger, logging.WARNING) as captured:
            var1 = _faker.slug()
            var2 = _faker.slug()
            self.custom_error.log_internal_message(logger, {"var1": var1, "var2": var2})

            self.assertIn(str(self.error_code), captured.output[0])
            self.assertIn(
                "Longer internal message {}, {}".format(var1, var2), captured.output[1]
            )

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_notify_sources(self, mock_notify_sources):
        """Test that notify calls notify_application_availability."""
        account_number = str(_faker.pyint())
        app_id = _faker.pyint()
        self.custom_error.notify(account_number, app_id)
        mock_notify_sources.delay.assert_called_once_with(
            account_number,
            app_id,
            availability_status="unavailable",
            availability_status_error="Message including {}".format(self.error_code),
        )
