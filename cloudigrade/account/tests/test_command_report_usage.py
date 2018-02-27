"""Collection of tests for the Report Usage management command."""
import datetime
import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from account.management.commands.report_usage import reports
from account.tests import helper as account_helper
from util.tests import helper as util_helper


DAYS_31 = 24. * 60 * 60 * 31
HOURS_15 = 15. * 60 * 60
HOURS_10 = 10. * 60 * 60
HOURS_5 = 5. * 60 * 60


class ReportUsageArgumentsTest(TestCase):
    """Report Usage management command test case for CLI argument handling."""

    def setUp(self):
        """Set up commonly used data for each test."""
        self.account = account_helper.generate_account()

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


class ReportUsageTestMixin(object):
    """Mixin for common functions across different ReportUsage*Test classes."""

    def generate_events_get_identifier(self, powered_times, instance):
        """
        Generate events in the DB and return the first one's identifier.

        Args:
            powered_times (list[tuple]): Time periods Instance is powered on.
            instance (account.Instance): Which instance has the events.

        Returns:
            str: The first event's product_identifier.

        """
        events = account_helper.generate_instance_events(
            instance, powered_times
        )
        return events[0].product_identifier

    def assert_report_usage_for_events(self, expected_totals):
        """
        Assert report_usage produces correct output for provided timed events.

        Args:
            expected_totals (dict): the expected totals data struct
        """
        expected_results = {str(self.account.account_id): expected_totals}
        expected_stdout = json.dumps(expected_results)

        out = StringIO()
        call_command(
            'report_usage',
            self.start,
            self.end,
            self.account.account_id,
            stdout=out
        )
        actual_stdout = out.getvalue().strip()
        self.assertEqual(actual_stdout, expected_stdout)


class ReportUsageOneAccountOneInstanceTest(TestCase, ReportUsageTestMixin):
    """Report Usage management command test case for 1 account, 1 instance."""

    def setUp(self):
        """Set up commonly used data for each test."""
        self.account = account_helper.generate_account()
        self.instance = account_helper.generate_instance(self.account)
        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0).isoformat()
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0).isoformat()

    def generate_events_get_identifier(self, powered_times):
        """
        Generate events in the DB and return the first one's identifier.

        Args:
            powered_times (list[tuple]): Time periods Instance is powered on.

        Returns:
            str: If any were created, the first event's product_identifier.

        """
        return super(ReportUsageOneAccountOneInstanceTest, self)\
            .generate_events_get_identifier(powered_times, self.instance)

    def test_report_no_events(self):
        """
        Assert empty-like report when no events exist.

        The instance's running time in the window would look like:
            [                               ]
        """
        self.assert_report_usage_for_events({})

    def test_report_on_in_off_in(self):
        """
        Assert report for 5 hours powered in the period.

        This test asserts counting when there's a both power-on event and a
        power-off event 5 hours apart inside the report window.

        The instance's running time in the window would look like:
            [        ##                     ]
        """
        powered_times = (
            (util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
             util_helper.utc_dt(2018, 1, 10, 5, 0, 0)),
        )
        identifier = self.generate_events_get_identifier(powered_times)
        expected = {identifier: HOURS_5}
        self.assert_report_usage_for_events(expected)

    def test_report_on_in_on_in_off_in(self):
        """
        Assert report for 5 hours powered in the period.

        This test asserts counting when there's a both power-on event, a second
        bogus power-on even 1 hour later, and a power-off event 4 more hours
        later, all inside the report window.

        The instance's running time in the window would look like:
            [        ##                     ]
        """
        powered_times = (
            (util_helper.utc_dt(2018, 1, 10, 0, 0, 0), None),
            (util_helper.utc_dt(2018, 1, 10, 1, 0, 0),
             util_helper.utc_dt(2018, 1, 10, 5, 0, 0)),
        )
        identifier = self.generate_events_get_identifier(powered_times)
        expected = {identifier: HOURS_5}
        self.assert_report_usage_for_events(expected)

    def test_report_on_before_off_in(self):
        """
        Assert report for 5 hours powered in the period.

        This test asserts counting when there was a power-on event before the
        report window starts and a power-off event 5 hours into the window.

        The instance's running time in the window would look like:
            [##                             ]
        """
        powered_times = (
            (util_helper.utc_dt(2017, 1, 1, 0, 0, 0),
             util_helper.utc_dt(2018, 1, 1, 5, 0, 0)),
        )
        identifier = self.generate_events_get_identifier(powered_times)
        expected = {identifier: HOURS_5}
        self.assert_report_usage_for_events(expected)

    def test_report_on_in(self):
        """
        Assert report for 5 hours powered in the period.

        This test asserts counting when there was only a power-on event 5 hours
        before the report window ends.

        The instance's running time in the window would look like:
            [                             ##]
        """
        powered_times = (
            (util_helper.utc_dt(2018, 1, 31, 19, 0, 0), None),
        )
        identifier = self.generate_events_get_identifier(powered_times)
        expected = {identifier: HOURS_5}
        self.assert_report_usage_for_events(expected)

    def test_report_on_before_off_never(self):
        """
        Assert report for all 31 days powered in the period.

        This test asserts counting when there was a power-on event before
        the report window starts and nothing else.

        The instance's running time in the window would look like:
            [###############################]
        """
        powered_times = (
            (util_helper.utc_dt(2017, 1, 1), None),
        )
        identifier = self.generate_events_get_identifier(powered_times)
        expected = {identifier: DAYS_31}
        self.assert_report_usage_for_events(expected)

    def test_report_on_before_off_after(self):
        """
        Assert report for all 31 days powered in the period.

        This test asserts counting when there was a power-on event before
        the report window starts and a power-off event after the window ends.

        The instance's running time in the window would look like:
            [###############################]
        """
        powered_times = (
            (util_helper.utc_dt(2017, 1, 1),
             util_helper.utc_dt(2019, 1, 1)),
        )
        identifier = self.generate_events_get_identifier(powered_times)
        expected = {identifier: DAYS_31}
        self.assert_report_usage_for_events(expected)

    def test_report_on_before_off_in_on_in_off_in_on_in(self):
        """
        Assert report for 15 hours powered in the period.

        This test asserts counting when there was a power-on event before the
        reporting window start, a power-off event 5 hours into the window, a
        power-on event in the middle of the window, a power-off event 5 hours
        later, and a power-on event 5 hours before the window ends

        The instance's running time in the window would look like:
            [##            ##             ##]
        """
        powered_times = (
            (util_helper.utc_dt(2017, 1, 1, 0, 0, 0),
             util_helper.utc_dt(2018, 1, 1, 5, 0, 0)),
            (util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
             util_helper.utc_dt(2018, 1, 10, 5, 0, 0)),
            (util_helper.utc_dt(2018, 1, 31, 19, 0, 0), None),
        )
        identifier = self.generate_events_get_identifier(powered_times)
        expected = {identifier: HOURS_15}
        self.assert_report_usage_for_events(expected)


class ReportUsageOneAccountTwoInstancesTest(TestCase, ReportUsageTestMixin):
    """
    Report Usage management command test case for 2 similar instances.

    This simulates the case of one customer having two instances running the
    same version of RHEL using the same AMI in the same subnet of the same
    instance size.
    """

    def setUp(self):
        """Set up commonly used data for each test."""
        self.account = account_helper.generate_account()
        self.instance_1 = account_helper.generate_instance(self.account)
        self.instance_2 = account_helper.generate_instance(self.account)
        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0).isoformat()
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0).isoformat()

    def test_report_no_events(self):
        """Assert empty-like report when no events exist.

        The instances' running times in the window would look like:
            [                               ]
            [                               ]
        """
        self.assert_report_usage_for_events({})

    def test_report_on_times_not_overlapping(self):
        """
        Assert report for 10 hours powered in the period.

        This test asserts counting when one instance was on for 5 hours
        and another instance was on for 5 hours at a different time.

        The instances' running times in the window would look like:
            [        ##                     ]
            [                    ##         ]
        """
        powered_times = (
            (util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
             util_helper.utc_dt(2018, 1, 10, 5, 0, 0)),
        )
        events = account_helper.generate_instance_events(
            self.instance_1, powered_times
        )

        identifier = events[0].product_identifier
        ec2_ami_id = events[0].ec2_ami_id
        instance_type = events[0].instance_type
        subnet = events[0].subnet

        powered_times = (
            (util_helper.utc_dt(2018, 1, 20, 0, 0, 0),
             util_helper.utc_dt(2018, 1, 20, 5, 0, 0)),
        )
        account_helper.generate_instance_events(
            self.instance_2, powered_times,
            ec2_ami_id=ec2_ami_id,
            instance_type=instance_type,
            subnet=subnet,
        )
        expected = {identifier: HOURS_10}
        self.assert_report_usage_for_events(expected)

    def test_report_on_times_overlapping(self):
        """
        Assert report for 10 hours powered in the period.

        This test asserts counting when one instance was on for 5 hours
        and another instance was on for 5 hours at a another time that overlaps
        with the first by 2.5 hours.

        The instances' running times in the window would look like:
            [        ##                     ]
            [         ##                    ]
        """
        powered_times = (
            (util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
             util_helper.utc_dt(2018, 1, 10, 5, 0, 0)),
        )
        events = account_helper.generate_instance_events(
            self.instance_1, powered_times
        )

        identifier = events[0].product_identifier
        ec2_ami_id = events[0].ec2_ami_id
        instance_type = events[0].instance_type
        subnet = events[0].subnet

        powered_times = (
            (util_helper.utc_dt(2018, 1, 10, 2, 30, 0),
             util_helper.utc_dt(2018, 1, 10, 7, 30, 0)),
        )
        account_helper.generate_instance_events(
            self.instance_2, powered_times,
            ec2_ami_id=ec2_ami_id,
            instance_type=instance_type,
            subnet=subnet,
        )
        expected = {identifier: HOURS_10}
        self.assert_report_usage_for_events(expected)
