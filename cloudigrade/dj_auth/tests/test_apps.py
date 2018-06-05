"""Collection of tests for the App Configuration module."""
from django.apps import apps
from django.test import TestCase

from dj_auth.apps import DjAuthConfig


class AnalyzerConfigTest(TestCase):
    """Add Auth Configuration Test Case."""

    def test_apps(self):
        """Test the DJAuth app configuration."""
        self.assertEqual(DjAuthConfig.name, 'dj_auth')
        self.assertEqual(apps.get_app_config('dj_auth').name, 'dj_auth')
