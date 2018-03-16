"""Collection of tests for the App Configuration module."""
from django.apps import apps
from django.test import TestCase

from account.apps import AccountConfig


class AccountConfigTest(TestCase):
    """Add App Configuration Test Case."""

    def test_apps(self):
        """Test the Util app configuration."""
        self.assertEqual(AccountConfig.name, 'account')
        self.assertEqual(apps.get_app_config('account').name, 'account')
