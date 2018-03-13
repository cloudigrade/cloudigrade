"""Collection of tests for the reports module."""
from django.test import TestCase

from account import reports
from account.models import Account
from account.tests import helper as account_helper
from util.tests import helper as util_helper

DAYS_31 = 24. * 60 * 60 * 31
HOURS_15 = 15. * 60 * 60
HOURS_10 = 10. * 60 * 60
HOURS_5 = 5. * 60 * 60


class GetHourlyUsageNoDataTest(TestCase):
    """get_hourly_usage test case for when no data exists."""

    def test_usage_no_account(self):
        """Assert exception raised when reporting on bogus account ID."""
        with self.assertRaises(Account.DoesNotExist):
            reports.get_hourly_usage(
                account_id=util_helper.generate_dummy_aws_account_id(),
                start=util_helper.utc_dt(2018, 1, 1, 0, 0, 0),
                end=util_helper.utc_dt(2018, 2, 1, 0, 0, 0),
            )


class GetHourlyUsageTestMixin(object):
    """Mixin for common functions to use in GetHourlyUsage*Test classes."""

    def generate_events_get_identifier(self, powered_times, instance):
        # pylint: disable=no-self-use
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

    def assertHourlyUsage(self, expected_totals):
        # pylint: disable=invalid-name
        """
        Assert get_hourly_usage produces output matching expected totals.

        Note: this function is mixedCase to match Django TestCase style.

        Args:
            expected_totals (dict): the expected totals data struct
        """
        actual_results = reports.get_hourly_usage(
            self.start,
            self.end,
            self.account.account_id
        )
        self.assertEqual(actual_results, expected_totals)


class GetHourlyUsage1Account1InstanceTest(TestCase, GetHourlyUsageTestMixin):
    """get_hourly_usage test case for one account with one instance."""

    def setUp(self):
        """Set up commonly used data for each test."""
        self.account = account_helper.generate_account()
        self.instance = account_helper.generate_instance(self.account)
        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)

    def generate_events_get_identifier(self, powered_times):
        # pylint: disable=arguments-differ
        """
        Generate events in the DB and return the first one's identifier.

        Args:
            powered_times (list[tuple]): Time periods Instance is powered on.

        Returns:
            str: If any were created, the first event's product_identifier.

        """
        return super(GetHourlyUsage1Account1InstanceTest, self)\
            .generate_events_get_identifier(powered_times, self.instance)

    def test_usage_no_events(self):
        """
        Assert empty-like report when no events exist.

        The instance's running time in the window would look like:
            [                               ]
        """
        self.assertHourlyUsage({})

    def test_usage_on_in_off_in(self):
        """
        Assert usage for 5 hours powered in the period.

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
        self.assertHourlyUsage(expected)

    def test_usage_on_in_on_in_off_in(self):
        """
        Assert usage for 5 hours powered in the period.

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
        self.assertHourlyUsage(expected)

    def test_usage_on_before_off_in(self):
        """
        Assert usage for 5 hours powered in the period.

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
        self.assertHourlyUsage(expected)

    def test_usage_on_in(self):
        """
        Assert usage for 5 hours powered in the period.

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
        self.assertHourlyUsage(expected)

    def test_usage_on_before_off_never(self):
        """
        Assert usage for all 31 days powered in the period.

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
        self.assertHourlyUsage(expected)

    def test_usage_on_before_off_after(self):
        """
        Assert usage for all 31 days powered in the period.

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
        self.assertHourlyUsage(expected)

    def test_usage_on_before_off_in_on_in_off_in_on_in(self):
        """
        Assert usage for 15 hours powered in the period.

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
        self.assertHourlyUsage(expected)


class GetHourlyUsage2SimilarInstancesTest(TestCase, GetHourlyUsageTestMixin):
    """
    get_hourly_usage test case for two similar instances.

    This simulates the case of one customer having two instances running the
    same version of RHEL using the same AMI in the same subnet of the same
    instance size.
    """

    def setUp(self):
        """Set up commonly used data for each test."""
        self.account = account_helper.generate_account()
        self.instance_1 = account_helper.generate_instance(self.account)
        self.instance_2 = account_helper.generate_instance(self.account)
        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)

    def test_usage_no_events(self):
        """Assert empty-like report when no events exist.

        The instances' running times in the window would look like:
            [                               ]
            [                               ]
        """
        self.assertHourlyUsage({})

    def test_usage_on_times_not_overlapping(self):
        """
        Assert usage for 10 hours powered in the period.

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
        self.assertHourlyUsage(expected)

    def test_usage_on_times_overlapping(self):
        """
        Assert usage for 10 hours powered in the period.

        This test asserts counting when one instance was on for 5 hours and
        another instance was on for 5 hours at a another time that overlaps
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
        self.assertHourlyUsage(expected)
