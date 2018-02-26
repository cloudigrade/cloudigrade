"""Collection of tests for the App Configuration module."""
from django.apps import apps
from django.test import TestCase
from analyzer.apps import AnalyzerConfig


class AnalyzerConfigTest(TestCase):
    """Add Analyzer Configuration Test Case."""

    def test_apps(self):
        """Test the Util app configuration."""
        self.assertEqual(AnalyzerConfig.name, 'analyzer')
        self.assertEqual(apps.get_app_config('analyzer').name, 'analyzer')
