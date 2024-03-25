"""Collection of tests for the App Configuration module."""

from django.apps import apps
from django.test import TestCase

from util.apps import UtilConfig


class UtilConfigTest(TestCase):
    """Add App Configuration Test Case."""

    def test_apps(self):
        """Test the Util app configuration."""
        self.assertEqual(UtilConfig.name, "util")
        self.assertEqual(apps.get_app_config("util").name, "util")
