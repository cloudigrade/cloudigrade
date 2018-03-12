"""Collection of tests for the reports module."""
from unittest.mock import Mock

from django.test import TestCase

import account.exceptions
from account import reports


class GetHourlyUsageTest(TestCase):
    """get_time_usage test case."""

    def test_usage_unknown_cloud(self):
        """Assert function fails for an unknown cloud provider."""
        with self.assertRaises(account.exceptions.InvalidCloudProviderError):
            reports.get_time_usage(Mock(), Mock(), Mock(), Mock())
