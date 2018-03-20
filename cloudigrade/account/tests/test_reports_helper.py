"""Collection of tests for the reports.helper module."""
from unittest.mock import Mock, patch

from django.test import TestCase

from account import AWS_PROVIDER_STRING
from account.exceptions import InvalidCloudProviderError
from account.reports import helper


class GetReportHelperTest(TestCase):
    """get_report_helper test case."""

    def test_get_report_helper_aws(self):
        """Assert get_report_helper returns the correct class for 'aws'."""
        report_helper = helper.get_report_helper(AWS_PROVIDER_STRING, Mock())
        self.assertIsInstance(report_helper, helper.AwsReportHelper)

    def test_get_report_helper_not_in_cloud_providers(self):
        """Assert InvalidCloudProviderError if requesting invalid provider."""
        with self.assertRaises(InvalidCloudProviderError):
            helper.get_report_helper(Mock(), Mock())

    def test_get_report_helper_not_implemented(self):
        """
        Assert NotImplementedError if get_report_helper can't find a helper.

        This should be considered an extreme edge/corner case, and
        realistically this could only happy if we start adding support for a
        new cloud provider but fail to complete the new ReportHelper subclass.
        """
        provider = 'bogus-provider-name'
        with patch.object(helper, 'CLOUD_PROVIDERS', new={provider}):
            with self.assertRaises(NotImplementedError):
                helper.get_report_helper(provider, Mock())
