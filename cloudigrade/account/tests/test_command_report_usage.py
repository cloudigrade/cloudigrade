"""Collection of tests for the Report Usage management command."""
import datetime
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from account.management.commands.report_usage import reports
from account.tests import helper as account_helper
from util.tests import helper as util_helper


class ReportUsageArgumentsTest(TestCase):
    """Report Usage management command test case for CLI argument handling."""

    def setUp(self):
        """Set up commonly used data for each test."""
        self.account = account_helper.generate_account()

    def test_args_dates_with_timezones(self):
        """Assert normal behavior when given dates with timezones."""
        start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0).isoformat()
        end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0).isoformat()

        with patch.object(reports, 'get_hourly_usage') as mock_get_hourly:
            mock_get_hourly.return_value = {}
            call_command(
                'report_usage',
                start,
                end,
                self.account.account_id,
                stdout=StringIO()
            )
            expected_start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
            expected_end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)
            mock_get_hourly.assert_called_with(
                expected_start,
                expected_end,
                self.account.account_id
            )

    def test_args_dates_without_timezones(self):
        """Assert CLI date args without timezones are set to UTC."""
        start = datetime.datetime(2018, 1, 1, 0, 0, 0).isoformat()
        end = datetime.datetime(2018, 2, 1, 0, 0, 0).isoformat()

        with patch.object(reports, 'get_hourly_usage') as mock_get_hourly:
            mock_get_hourly.return_value = {}
            call_command(
                'report_usage',
                start,
                end,
                self.account.account_id,
                stdout=StringIO()
            )
            expected_start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
            expected_end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)
            mock_get_hourly.assert_called_with(
                expected_start,
                expected_end,
                self.account.account_id
            )
