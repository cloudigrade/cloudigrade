"""Collection of tests for the reports module."""
import faker
from django.test import TestCase

from account import reports
from account.models import InstanceEvent
from account.tests import helper as account_helper
from util.tests import helper as util_helper

HOUR = 60. * 60
DAY = HOUR * 24
HOURS_5 = HOUR * 5
HOURS_10 = HOUR * 10
HOURS_15 = HOUR * 15
DAYS_31 = DAY * 31

_faker = faker.Faker()


class ReportTestBase(TestCase):
    """Base class for reporting tests that require some data setup."""

    def setUp(self):
        """
        Set up commonly used data for each test.

        From this rich combination of data, we should have enough data for some
        interesting tests! If you think your test needs more, consider adding
        to this based class setup.

        The rough hierarchy of initial objects looks something like this:

            user_1:
                image_plain
                image_rhel
                image_ocp
                image_rhel_ocp
                image_windows
                account_1:
                    plain_instance
                    windows_instance
                    rhel_instance
                    openshift_instance
                    rhel_ocp_instance
                    noimage_instance
                account_2:
                    None

            user_2:
                account_3:
                    None
                account_4:
                    None

            user_super:
                None
        """
        self.user_1 = util_helper.generate_test_user()
        self.user_2 = util_helper.generate_test_user()
        self.user_super = util_helper.generate_test_user(is_superuser=True)

        self.account_1 = account_helper.generate_aws_account(
            user=self.user_1, name=_faker.bs())
        self.account_2 = account_helper.generate_aws_account(
            user=self.user_1, name=_faker.bs())
        self.account_3 = account_helper.generate_aws_account(
            user=self.user_2, name=_faker.bs())
        self.account_4 = account_helper.generate_aws_account(
            user=self.user_2, name=_faker.bs())

        self.instance_type = util_helper.get_random_instance_type()

        self.instance = util_helper.SOME_EC2_INSTANCE_TYPES[self.instance_type]

        self.image_plain = account_helper.generate_aws_image(
            self.account_1.aws_account_id)
        self.image_windows = account_helper.generate_aws_image(
            self.account_1.aws_account_id, is_windows=True)
        self.image_rhel = account_helper.generate_aws_image(
            self.account_1.aws_account_id, rhel_detected=True)
        self.image_ocp = account_helper.generate_aws_image(
            self.account_1.aws_account_id, openshift_detected=True)
        self.image_rhel_ocp = account_helper.generate_aws_image(
            self.account_1.aws_account_id, rhel_detected=True,
            openshift_detected=True)

        self.plain_instance = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_plain
        )
        self.windows_instance = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_windows
        )
        self.rhel_instance = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        self.openshift_instance = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_ocp
        )
        self.rhel_ocp_instance = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel_ocp
        )

        self.noimage_instance = account_helper.generate_aws_instance(
            account=self.account_1, no_image=True
        )

        # Report on "month of January in 2018"
        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)

        account_helper.generate_aws_ec2_definitions()

    def generate_runs(self, powered_times, instance=None, image=None):
        """
        Generate runs saved to the DB and returned.

        Args:
            powered_times (list[tuple]): Time periods instance is powered on.
            instance (Instance): Optional which instance has the run. If
                not specified, default is self.instance_1.
            image (AwsMachineImage): Optional which image seen in the runs.
                If not specified, default is self.image_rhel.

        Returns:
            list[Run]: The list of runs

        """
        if instance is None:
            instance = self.rhel_instance
        if image is None:
            image = self.image_rhel
        runs = account_helper.generate_runs(
            instance,
            powered_times,
            image=image,
            instance_type=self.instance_type
        )
        return runs

    def generate_events(self, powered_times, instance=None, image=None):
        """
        Generate events saved to the DB and returned.

        Args:
            powered_times (list[tuple]): Time periods instance is powered on.
            instance (Instance): Optional which instance has the events. If
                not specified, default is self.instance_1.
            image (AwsMachineImage): Optional which image seen in the events.
                If not specified, default is self.image_rhel.

        Returns:
            list[InstanceEvent]: The list of events

        """
        if instance is None:
            instance = self.rhel_instance
        if image is None:
            image = self.image_rhel
        events = account_helper.generate_aws_instance_events(
            instance,
            powered_times,
            image.ec2_ami_id,
            instance_type=self.instance_type
        )
        return events


class GetDailyUsageTestBase(ReportTestBase):
    """Base class for testing get_daily_usage with additional assertions."""

    def assertTotalRunningTimes(self, results, rhel=0, openshift=0,
                                rhel_memory=0, openshift_memory=0,
                                rhel_vcpu=0, openshift_vcpu=0):
        """Assert total expected running times for rhel and openshift."""
        self.assertEqual(sum((
            day['rhel_runtime_seconds'] for day in results['daily_usage']
        )), rhel)
        self.assertEqual(sum((
            day['openshift_runtime_seconds'] for day in results['daily_usage']
        )), openshift)
        self.assertEqual(sum((
            day['rhel_memory_seconds'] for day in results['daily_usage']
        )), rhel_memory)
        self.assertEqual(sum((
            day['openshift_memory_seconds'] for day in results['daily_usage']
        )), openshift_memory)
        self.assertEqual(sum((
            day['rhel_vcpu_seconds'] for day in results['daily_usage']
        )), rhel_vcpu)
        self.assertEqual(sum((
            day['openshift_vcpu_seconds'] for day in results['daily_usage']
        )), openshift_vcpu)

    def assertDaysSeen(self, results, rhel=0, openshift=0):
        """Assert expected days seen having rhel and openshift instances."""
        self.assertEqual(sum((
            1 for day in results['daily_usage']
            if day['rhel_instances'] > 0
        )), rhel)
        self.assertEqual(sum((
            1 for day in results['daily_usage']
            if day['openshift_instances'] > 0
        )), openshift)

    def assertInstancesSeen(self, results, rhel=0, openshift=0):
        """Assert total expected numbers of rhel and openshift instances."""
        self.assertEqual(results['instances_seen_with_rhel'], rhel)
        self.assertEqual(results['instances_seen_with_openshift'], openshift)

    def assertNoActivityFound(self, results):
        """Assert no relevant activity found in the report results."""
        self.assertTotalRunningTimes(results)
        self.assertDaysSeen(results)
        self.assertInstancesSeen(results)


class GetDailyUsageNoReportableActivity(GetDailyUsageTestBase):
    """get_daily_usage for cases that should produce no report output."""

    def test_no_runs(self):
        """Assert empty report when no events exist."""
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertNoActivityFound(results)

    def test_runs_only_in_past(self):
        """Assert empty report when events exist only in the past."""
        powered_times = (
            (
                util_helper.utc_dt(2017, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2017, 1, 10, 0, 0, 0)
            ),
        )
        self.generate_runs(powered_times)
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertNoActivityFound(results)

    def test_runs_only_in_future(self):
        """Assert empty report when events exist only in the future."""
        powered_times = (
            (
                util_helper.utc_dt(2019, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 10, 0, 0, 0)
            ),
        )
        self.generate_runs(powered_times)
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertNoActivityFound(results)

    def test_runs_in_other_user_account(self):
        """Assert empty report when events exist only for a different user."""
        powered_times = (
            (
                util_helper.utc_dt(2019, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 10, 0, 0, 0)
            ),
        )
        self.generate_runs(powered_times)
        results = reports.get_daily_usage(self.user_2.id, self.start, self.end)
        self.assertNoActivityFound(results)

    def test_runs_not_rhel_not_openshift(self):
        """Assert empty report when events exist only for plain images."""
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0)
            ),
        )
        self.generate_runs(
            powered_times, instance=self.plain_instance, image=self.image_plain
        )
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertNoActivityFound(results)


class GetDailyUsageBasicInstanceTest(GetDailyUsageTestBase):
    """get_daily_usage tests for an account with one relevant RHEL instance."""

    def test_usage_on_in_off_in(self):
        """
        Assert usage for 5 hours powered in the period.

        This test asserts counting when there's a complete run
        5 hours apart inside the report window.

        The instance's running time in the window would look like:
            [        ##                     ]
        """
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        self.generate_runs(powered_times)
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)

        self.assertTotalRunningTimes(
            results,
            rhel=HOURS_5,
            rhel_memory=HOURS_5 * self.instance['memory'],
            rhel_vcpu=HOURS_5 * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=1)
        self.assertInstancesSeen(results, rhel=1)

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
            (
                util_helper.utc_dt(2018, 1, 10, 1, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        events = self.generate_events(powered_times)

        account_helper.recalculate_runs_from_events(events)

        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=HOURS_5,
            rhel_memory=HOURS_5 * self.instance['memory'],
            rhel_vcpu=HOURS_5 * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=1)
        self.assertInstancesSeen(results, rhel=1)

    def test_usage_on_before_off_in(self):
        """
        Assert usage for 5 hours powered in the period.

        This test asserts counting when there was a power-on event before the
        report window starts and a power-off event 5 hours into the window.

        The instance's running time in the window would look like:
            [##                             ]
        """
        powered_times = (
            (
                util_helper.utc_dt(2017, 1, 1, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 1, 5, 0, 0)
            ),
        )
        self.generate_runs(powered_times)
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=HOURS_5,
            rhel_memory=HOURS_5 * self.instance['memory'],
            rhel_vcpu=HOURS_5 * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=1)
        self.assertInstancesSeen(results, rhel=1)

    def test_usage_on_in(self):
        """
        Assert usage for 5 hours powered in the period.

        This test asserts counting when there was only a power-on event 5 hours
        before the report window ends.

        The instance's running time in the window would look like:
            [                             ##]
        """
        powered_times = ((util_helper.utc_dt(2018, 1, 31, 19, 0, 0), None),)
        self.generate_runs(powered_times)
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=HOURS_5,
            rhel_memory=HOURS_5 * self.instance['memory'],
            rhel_vcpu=HOURS_5 * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=1)
        self.assertInstancesSeen(results, rhel=1)

    def test_usage_on_over_multiple_days_then_off(self):
        """
        Assert usage when powered on over multiple days.

        This test asserts counting when there was a power-on event at the start
        of the reporting window start, several days pass, and then a power-off
        event before the window ends.

        The instance's running time in the window would look like:
            [######                         ]
        """
        powered_times = (
            (
                util_helper.utc_dt(2017, 1, 1, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 6, 5, 0, 0)
            ),
        )
        self.generate_runs(powered_times)
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=DAY * 5 + HOURS_5,
            rhel_memory=(DAY * 5 + HOURS_5) * self.instance['memory'],
            rhel_vcpu=(DAY * 5 + HOURS_5) * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=6)
        self.assertInstancesSeen(results, rhel=1)

    def test_usage_on_before_off_never(self):
        """
        Assert usage for all 31 days powered in the period.

        This test asserts counting when there was a power-on event before
        the report window starts and nothing else.

        The instance's running time in the window would look like:
            [###############################]
        """
        powered_times = ((util_helper.utc_dt(2017, 1, 1), None),)
        self.generate_runs(powered_times)
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=DAYS_31,
            rhel_memory=DAYS_31 * self.instance['memory'],
            rhel_vcpu=DAYS_31 * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=31)
        self.assertInstancesSeen(results, rhel=1)

    def test_usage_on_before_off_after(self):
        """
        Assert usage for all 31 days powered in the period.

        This test asserts counting when there was a power-on event before
        the report window starts and a power-off event after the window ends.

        The instance's running time in the window would look like:
            [###############################]
        """
        powered_times = (
            (util_helper.utc_dt(2017, 1, 1), util_helper.utc_dt(2019, 1, 1)),
        )
        self.generate_runs(powered_times)
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=DAYS_31,
            rhel_memory=DAYS_31 * self.instance['memory'],
            rhel_vcpu=DAYS_31 * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=31)
        self.assertInstancesSeen(results, rhel=1)

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
            (
                util_helper.utc_dt(2017, 1, 1, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 1, 5, 0, 0)
            ),
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
            (util_helper.utc_dt(2018, 1, 31, 19, 0, 0), None),
        )
        self.generate_runs(powered_times)
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=HOURS_15,
            rhel_memory=HOURS_15 * self.instance['memory'],
            rhel_vcpu=HOURS_15 * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=3)
        self.assertInstancesSeen(results, rhel=1)

    def test_usage_nonexistent_instance_type(self):
        """Assert memory and vcpu usage is 0, if instance type is not valid."""
        powered_time = (
            util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
            util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
        )
        account_helper.generate_single_run(
            self.rhel_ocp_instance,
            powered_time,
            image=self.image_rhel_ocp,
            instance_type='i-dont-exist'
        )
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=HOURS_5,
            rhel_memory=0,
            rhel_vcpu=0,
            openshift=HOURS_5,
            openshift_memory=0,
            openshift_vcpu=0
        )
        self.assertDaysSeen(results, rhel=1, openshift=1)
        self.assertInstancesSeen(results, rhel=1, openshift=1)


class GetDailyUsageTwoRhelInstancesTest(GetDailyUsageTestBase):
    """
    get_daily_usage tests for 1 account with 2 RHEL instances.

    This simulates the case of one customer having two instances running the
    same RHEL image at different times.
    """

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
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        self.generate_runs(powered_times)

        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 20, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 20, 5, 0, 0)
            ),
        )
        rhel_instance_2 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        self.generate_runs(powered_times, instance=rhel_instance_2)

        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=HOURS_10,
            rhel_memory=HOURS_10 * self.instance['memory'],
            rhel_vcpu=HOURS_10 * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=2)
        self.assertInstancesSeen(results, rhel=2)

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
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        rhel_instance_1 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )

        self.generate_runs(powered_times, rhel_instance_1)

        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 2, 30, 0),
                util_helper.utc_dt(2018, 1, 10, 7, 30, 0)
            ),
        )
        rhel_instance_2 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )

        self.generate_runs(powered_times, rhel_instance_2)

        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=HOURS_10,
            rhel_memory=HOURS_10 * self.instance['memory'],
            rhel_vcpu=HOURS_10 * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=1)
        self.assertInstancesSeen(results, rhel=2)


class GetDailyUsageOneRhelOneOpenShiftInstanceTest(GetDailyUsageTestBase):
    """
    get_daily_usage tests for 1 account with 1 RHEL and 1 OpenShift instance.

    This simulates the case of one customer having one instance using a RHEL
    image and one instance using an OpenShift image running at different times.
    """

    def test_usage_on_times_not_overlapping(self):
        """
        Assert usage for 5 hours RHEL and 5 hours OpenShift in the period.

        This test asserts counting when the RHEL instance was on for 5 hours
        and the OpenShift instance was on for 5 hours at a different time.

        The instances' running times in the window would look like:
            [        ##                     ]
            [                    ##         ]
        """
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        self.generate_runs(
            powered_times, self.rhel_instance, self.image_rhel
        )

        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 20, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 20, 5, 0, 0)
            ),
        )
        self.generate_runs(
            powered_times, self.openshift_instance, self.image_ocp
        )

        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=HOURS_5,
            openshift=HOURS_5,
            rhel_memory=HOURS_5 * self.instance['memory'],
            rhel_vcpu=HOURS_5 * self.instance['vcpu'],
            openshift_memory=HOURS_5 * self.instance['memory'],
            openshift_vcpu=HOURS_5 * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=1, openshift=1)
        self.assertInstancesSeen(results, rhel=1, openshift=1)

    def test_usage_on_times_overlapping(self):
        """
        Assert overlapping RHEL and OpenShift times are reported separately.

        This test asserts counting when the RHEL instance was on for 5 hours
        and the OpenShift instance was on for 5 hours at a another time that
        overlaps with the first by 2.5 hours.

        The instances' running times in the window would look like:
            [        ##                     ]
            [         ##                    ]
        """
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        self.generate_runs(
            powered_times, self.rhel_instance, self.image_rhel
        )

        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 2, 30, 0),
                util_helper.utc_dt(2018, 1, 10, 7, 30, 0)
            ),
        )
        self.generate_runs(
            powered_times, self.openshift_instance, self.image_ocp
        )

        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertTotalRunningTimes(
            results,
            rhel=HOURS_5,
            openshift=HOURS_5,
            rhel_memory=HOURS_5 * self.instance['memory'],
            rhel_vcpu=HOURS_5 * self.instance['vcpu'],
            openshift_memory=HOURS_5 * self.instance['memory'],
            openshift_vcpu=HOURS_5 * self.instance['vcpu']
        )
        self.assertDaysSeen(results, rhel=1, openshift=1)
        self.assertInstancesSeen(results, rhel=1, openshift=1)


class GetDailyUsageComplexInstancesTest(GetDailyUsageTestBase):
    """get_time_usage tests for 1 account and several instances."""

    def test_several_instances_with_whole_days(self):
        """
        Assert correct report for instances with various run times.

        The RHEL-only running times over the month would look like:

            [ ####      ##                  ]
            [  ##                ##         ]

        The plain running times over the month would look like:

            [  #####                        ]

        The OpenShift-only running times over the month would look like:

            [                  ###          ]

        The RHEL+OpenShift running times over the month would look like:

            [        #          ##          ]
        """
        powered_times_1 = (
            (
                # running for 4 days (2, 3, 4, 5)
                util_helper.utc_dt(2018, 1, 2, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 6, 0, 0, 0)
            ),
            (
                # running for 2 days (12, 13)
                util_helper.utc_dt(2018, 1, 12, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 14, 0, 0, 0)
            ),
        )
        rhel_instance_1 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        account_helper.generate_runs(
            rhel_instance_1,
            powered_times_1,
            image=self.image_rhel,
            instance_type=self.instance_type
        )

        powered_times_2 = (
            (
                # running for 2 days (3, 5)
                util_helper.utc_dt(2018, 1, 3, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
            ),
            (
                # running for 2 days (21, 22)
                util_helper.utc_dt(2018, 1, 21, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 23, 0, 0, 0)
            ),
        )
        rhel_instance_2 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        account_helper.generate_runs(
            rhel_instance_2,
            powered_times_2,
            image=self.image_rhel,
            instance_type=self.instance_type
        )

        powered_times_3 = (
            (
                # running for 5 days (3, 4, 5, 6, 7)
                util_helper.utc_dt(2018, 1, 3, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 8, 0, 0, 0)
            ),
        )
        account_helper.generate_runs(
            self.plain_instance,
            powered_times_3,
            image=self.image_plain,
            instance_type=self.instance_type
        )

        powered_times_4 = (
            (
                # running for 3 days (19, 20, 21)
                util_helper.utc_dt(2018, 1, 19, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 22, 0, 0, 0)
            ),
        )
        account_helper.generate_runs(
            self.openshift_instance,
            powered_times_4,
            image=self.image_ocp,
            instance_type=self.instance_type
        )

        powered_times_5 = (
            (
                # running for 1 day (9)
                util_helper.utc_dt(2018, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0)
            ),
            (
                # running for 2 days (20, 21)
                util_helper.utc_dt(2018, 1, 20, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 22, 0, 0, 0)
            ),
        )
        account_helper.generate_runs(
            self.rhel_ocp_instance,
            powered_times_5,
            image=self.image_rhel_ocp,
            instance_type=self.instance_type
        )

        results = reports.get_daily_usage(
            self.account_1.user_id,
            self.start,
            self.end,
        )

        self.assertEqual(len(results['daily_usage']), 31)
        self.assertInstancesSeen(results, rhel=3, openshift=2)

        # total of rhel seconds should be 13 days worth of seconds.
        # total of openshift seconds should be 6 days worth of seconds.
        self.assertTotalRunningTimes(
            results,
            rhel=DAY * 13,
            openshift=DAY * 6,
            rhel_memory=DAY * 13 * self.instance['memory'],
            rhel_vcpu=DAY * 13 * self.instance['vcpu'],
            openshift_memory=DAY * 6 * self.instance['memory'],
            openshift_vcpu=DAY * 6 * self.instance['vcpu']
        )

        # number of individual days in which we saw anything rhel is 10
        # number of individual days in which we saw anything openshift is 4
        self.assertDaysSeen(results, rhel=10, openshift=4)

        # number of days in which we saw 2 rhel running all day is 3
        self.assertEqual(sum((
            1 for day in results['daily_usage']
            if day['rhel_runtime_seconds'] == DAY * 2
        )), 3)

        # number of days in which we saw 1 rhel running all day is 7
        self.assertEqual(sum((
            1 for day in results['daily_usage']
            if day['rhel_runtime_seconds'] == DAY
        )), 7)

        # number of days in which we saw 1 openshift running all day is 2
        self.assertEqual(sum((
            1 for day in results['daily_usage']
            if day['openshift_runtime_seconds'] == DAY * 2
        )), 2)

        # number of days in which we saw 2 openshift running all day is 2
        self.assertEqual(sum((
            1 for day in results['daily_usage']
            if day['openshift_runtime_seconds'] == DAY * 2
        )), 2)


class GetDailyUsageInstancesWithUnknownImagesActivity(GetDailyUsageTestBase):
    """get_daily_usage for running instance with no known images."""

    def generate_runs(self, powered_times, instance=None):
        """
        Generate events without an image saved to the DB and returned.

        Args:
            powered_times (list[tuple]): Time periods instance is powered on.
            instance (Instance): Optional which instance has the events. If
                not specified, default is self.noimage_instance.

        Returns:
            list[InstanceEvent]: The list of events

        """
        if instance is None:
            instance = self.noimage_instance
        runs = account_helper.generate_runs(
            instance, powered_times, no_image=True,
        )
        return runs

    def test_events_without_images(self):
        """Assert empty report when the instance has no known images."""
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0)
            ),
        )
        self.generate_runs(powered_times)
        results = reports.get_daily_usage(self.user_1.id, self.start, self.end)
        self.assertNoActivityFound(results)


class GetCloudAccountOverview(TestCase):
    """Test that the CloudAccountOverview functions act correctly."""

    def setUp(self):
        """Set up commonly used data for each test."""
        # set up start & end dates and images
        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)
        self.account = account_helper.generate_aws_account()
        self.account.created_at = util_helper.utc_dt(2017, 1, 1, 0, 0, 0)
        self.account.save()
        # set up an account created after the end date for testing
        self.account_after_end = account_helper.generate_aws_account()
        self.account_after_end.created_at = \
            util_helper.utc_dt(2018, 3, 1, 0, 0, 0)
        self.account_after_end.save()
        # set up an account created on the end date for testing
        self.account_on_end = account_helper.generate_aws_account()
        self.account_on_end.created_at = self.end
        self.account_on_end.save()
        self.windows_image = account_helper.generate_aws_image(
            is_encrypted=False,
            is_windows=True,
        )
        self.rhel_image = account_helper.generate_aws_image(
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            rhel_detected=True,
            openshift_detected=False,
        )
        self.openshift_image = account_helper.generate_aws_image(
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            rhel_detected=False,
            openshift_detected=True,
        )
        self.openshift_image_challenged = account_helper.generate_aws_image(
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            rhel_detected=False,
            openshift_detected=True,
            openshift_challenged=True,
        )
        self.plain_image_both_challenged = account_helper.generate_aws_image(
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            rhel_detected=False,
            openshift_detected=False,
            rhel_challenged=True,
            openshift_challenged=True,
        )
        self.openshift_and_rhel_image = account_helper.generate_aws_image(
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            rhel_detected=True,
            openshift_detected=True,
        )
        self.windows_instance = account_helper.generate_aws_instance(
            self.account, image=self.windows_image
        )
        self.rhel_instance = account_helper.generate_aws_instance(
            self.account, image=self.rhel_image
        )
        self.openshift_instance = account_helper.generate_aws_instance(
            self.account, image=self.openshift_image
        )
        self.openshift_challenged_instance = \
            account_helper.generate_aws_instance(
                self.account, image=self.openshift_image_challenged
            )
        self.both_challenged_instance = account_helper.generate_aws_instance(
            self.account, image=self.plain_image_both_challenged
        )
        self.openshift_rhel_instance = account_helper.generate_aws_instance(
            self.account, image=self.openshift_and_rhel_image
        )

        self.start_future = util_helper.utc_dt(3000, 1, 1, 0, 0, 0)
        self.end_future = util_helper.utc_dt(3000, 2, 1, 0, 0, 0)

        account_helper.generate_aws_ec2_definitions()

        self.instance_type = util_helper.get_random_instance_type()
        self.instance = util_helper.SOME_EC2_INSTANCE_TYPES[self.instance_type]

    def assertExpectedAccountOverview(self, overview, account,
                                      images=0, instances=0,
                                      rhel_instances=0, openshift_instances=0,
                                      rhel_runtime_seconds=0.0,
                                      openshift_runtime_seconds=0.0,
                                      rhel_images_challenged=0,
                                      openshift_images_challenged=0,
                                      rhel_memory_seconds=0.0,
                                      openshift_memory_seconds=0.0,
                                      rhel_vcpu_seconds=0.0,
                                      openshift_vcpu_seconds=0.0):
        """Assert results match the expected account info and counters."""
        expected_overview = {
            'id': account.id,
            'cloud_account_id': account.cloud_account_id,
            'user_id': account.user_id,
            'type': account.cloud_type,
            'arn': account.account_arn,
            'creation_date': account.created_at,
            'name': account.name,
            'images': images,
            'instances': instances,
            'rhel_instances': rhel_instances,
            'openshift_instances': openshift_instances,
            'rhel_runtime_seconds': rhel_runtime_seconds,
            'openshift_runtime_seconds': openshift_runtime_seconds,
            'rhel_images_challenged': rhel_images_challenged,
            'openshift_images_challenged': openshift_images_challenged,
            'rhel_memory_seconds': rhel_memory_seconds,
            'openshift_memory_seconds': openshift_memory_seconds,
            'rhel_vcpu_seconds': rhel_vcpu_seconds,
            'openshift_vcpu_seconds': openshift_vcpu_seconds,
        }
        self.assertEqual(expected_overview, overview)

    def test_get_cloud_account_overview_no_events(self):
        """Assert an overview of an account with no events returns 0s."""
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        self.assertExpectedAccountOverview(overview, self.account)

    def test_get_cloud_account_overview_with_events(self):
        """Assert an account overview reports instances/images correctly."""
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        account_helper.generate_runs(
            self.windows_instance, powered_times,
            image=self.windows_image
        )
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        self.assertExpectedAccountOverview(overview, self.account,
                                           images=1, instances=1)

    def test_get_cloud_account_overview_with_rhel_image(self):
        """Assert an account overview with events reports rhel correctly."""
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        account_helper.generate_runs(
            self.windows_instance, powered_times,
            image=self.windows_image,
        )
        # in addition to instance_1's events, we are creating an event for
        # instance_2 with a rhel_image
        account_helper.generate_single_run(
            self.rhel_instance, (self.start, None),
            image=self.rhel_image,
            instance_type=self.instance_type
        )
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # we expect to find 2 total images, 2 total instances and 1 rhel
        # instance
        self.assertExpectedAccountOverview(
            overview, self.account, images=2, instances=2, rhel_instances=1,
            rhel_runtime_seconds=DAYS_31,
            rhel_memory_seconds=DAYS_31 * self.instance['memory'],
            rhel_vcpu_seconds=DAYS_31 * self.instance['vcpu']
        )

    def test_get_cloud_account_overview_with_openshift_image(self):
        """Assert an account overview with events reports correctly."""
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        account_helper.generate_runs(
            self.windows_instance, powered_times,
            image=self.windows_image,
        )
        # in addition to instance_1's events, we are creating an event for
        # instance_2 with an openshift_image
        account_helper.generate_single_run(
            self.openshift_instance, (self.start, None),
            image=self.openshift_image,
            instance_type=self.instance_type
        )
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # we expect to find 2 total images, 2 total instances and 1
        # openshift instance
        self.assertExpectedAccountOverview(
            overview, self.account, images=2, instances=2,
            openshift_instances=1, openshift_runtime_seconds=DAYS_31,
            openshift_memory_seconds=DAYS_31 * self.instance['memory'],
            openshift_vcpu_seconds=DAYS_31 * self.instance['vcpu']
        )

    def test_get_cloud_account_overview_with_openshift_and_rhel_image(self):
        """Assert an account overview reports openshift and rhel correctly."""
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        account_helper.generate_runs(
            self.windows_instance, powered_times,
            image=self.windows_image,
        )
        # in addition to instance_1's events, we are creating an event for
        # instance_2 with a rhel & openshift_image
        account_helper.generate_single_run(
            self.openshift_rhel_instance, (self.start, None),
            image=self.openshift_and_rhel_image,
            instance_type=self.instance_type
        )
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # we expect to find 2 total images, 2 total instances, 1 rhel instance
        # and 1 openshift instance
        self.assertExpectedAccountOverview(
            overview, self.account, images=2, instances=2, rhel_instances=1,
            openshift_instances=1, openshift_runtime_seconds=DAYS_31,
            rhel_runtime_seconds=DAYS_31,
            openshift_memory_seconds=DAYS_31 * self.instance['memory'],
            openshift_vcpu_seconds=DAYS_31 * self.instance['vcpu'],
            rhel_memory_seconds=DAYS_31 * self.instance['memory'],
            rhel_vcpu_seconds=DAYS_31 * self.instance['vcpu']
        )

    def test_get_cloud_account_overview_with_challenged_images(self):
        """Assert an account overview reports challenged images correctly."""
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )

        # This instance is both detected and challenged for openshift.
        account_helper.generate_runs(
            self.openshift_challenged_instance, powered_times,
            image=self.openshift_image_challenged,
            instance_type=self.instance_type
        )
        # This instance has no detection but has challenges for both rhel and
        # openshift.
        account_helper.generate_runs(
            self.both_challenged_instance, powered_times,
            image=self.plain_image_both_challenged,
            instance_type=self.instance_type
        )

        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # we expect to find 2 total images, 2 total instances, 1 rhel instance,
        # 1 openshift instance, 1 rhel challenged image, and 2 openshift
        # challenged images.
        self.assertExpectedAccountOverview(
            overview, self.account, images=2, instances=2,
            rhel_images_challenged=1, rhel_instances=1,
            rhel_runtime_seconds=HOURS_5,
            rhel_memory_seconds=HOURS_5 * self.instance['memory'],
            rhel_vcpu_seconds=HOURS_5 * self.instance['vcpu'],
            openshift_images_challenged=2, openshift_instances=1,
            openshift_runtime_seconds=HOURS_5,
            openshift_memory_seconds=HOURS_5 * self.instance['memory'],
            openshift_vcpu_seconds=HOURS_5 * self.instance['vcpu'],
        )

    def test_get_cloud_account_overview_with_two_instances_same_image(self):
        """Assert an account overview reports images correctly."""
        # Generate 2 rhel/openshift instances
        openshift_rhel_instance = account_helper.generate_aws_instance(
            self.account, image=self.openshift_and_rhel_image
        )
        openshift_rhel_instance2 = account_helper.generate_aws_instance(
            self.account, image=self.openshift_and_rhel_image
        )
        # generate event for instance_1 with the rhel/openshift image
        account_helper.generate_single_run(
            openshift_rhel_instance, (self.start, None),
            image=self.openshift_and_rhel_image,
            instance_type=self.instance_type
        )
        # generate event for instance_2 with the rhel/openshift image
        account_helper.generate_single_run(
            openshift_rhel_instance2, (self.start, None),
            image=self.openshift_and_rhel_image,
            instance_type=self.instance_type
        )
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # assert that we only find the one image
        self.assertExpectedAccountOverview(
            overview, self.account, images=1, instances=2,
            rhel_instances=2, openshift_instances=2,
            openshift_runtime_seconds=DAYS_31 * 2,
            rhel_runtime_seconds=DAYS_31 * 2,
            openshift_memory_seconds=DAYS_31 * 2 * self.instance['memory'],
            openshift_vcpu_seconds=DAYS_31 * 2 * self.instance['vcpu'],
            rhel_memory_seconds=DAYS_31 * 2 * self.instance['memory'],
            rhel_vcpu_seconds=DAYS_31 * 2 * self.instance['vcpu']
        )

    def test_get_cloud_account_overview_with_rhel(self):
        """Assert an account overview reports rhel correctly."""
        # generate event for instance_1 with the rhel/openshift image
        account_helper.generate_single_run(
            self.openshift_rhel_instance, (self.start, None),
            image=self.openshift_and_rhel_image,
            instance_type=self.instance_type
        )
        # generate event for instance_2 with the rhel image
        account_helper.generate_single_run(
            self.rhel_instance, (self.start, None),
            image=self.rhel_image,
            instance_type=self.instance_type
        )
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # assert that we only find the two rhel images
        self.assertExpectedAccountOverview(
            overview, self.account, images=2, instances=2,
            rhel_instances=2, openshift_instances=1,
            rhel_runtime_seconds=DAYS_31 * 2,
            openshift_runtime_seconds=DAYS_31,
            openshift_memory_seconds=DAYS_31 * self.instance['memory'],
            openshift_vcpu_seconds=DAYS_31 * self.instance['vcpu'],
            rhel_memory_seconds=DAYS_31 * 2 * self.instance['memory'],
            rhel_vcpu_seconds=DAYS_31 * 2 * self.instance['vcpu']
        )

    def test_get_cloud_account_overview_with_openshift(self):
        """Assert an account overview reports openshift correctly."""
        # generate run for instance_1 with the rhel/openshift image
        account_helper.generate_single_run(
            self.openshift_rhel_instance, (self.start, None),
            image=self.openshift_and_rhel_image,
            instance_type=self.instance_type
        )
        # generate run for instance_2 with the openshift image
        account_helper.generate_single_run(
            self.openshift_instance, (self.start, None),
            image=self.openshift_image,
            instance_type=self.instance_type
        )
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # assert that we only find the two openshift images
        self.assertExpectedAccountOverview(
            overview, self.account, images=2, instances=2,
            rhel_instances=1, openshift_instances=2,
            rhel_runtime_seconds=DAYS_31,
            openshift_runtime_seconds=DAYS_31 * 2,
            openshift_memory_seconds=DAYS_31 * 2 * self.instance['memory'],
            openshift_vcpu_seconds=DAYS_31 * 2 * self.instance['vcpu'],
            rhel_memory_seconds=DAYS_31 * self.instance['memory'],
            rhel_vcpu_seconds=DAYS_31 * self.instance['vcpu']
        )

    def test_get_cloud_account_overview_with_unknown_image(self):
        """Assert an account overview reports when images are unknown."""
        self.noimage_instance = account_helper.generate_aws_instance(
            self.account, no_image=True
        )
        self.noimage_instance2 = account_helper.generate_aws_instance(
            self.account, no_image=True
        )
        # generate run for instance_1 with unknown image
        account_helper.generate_single_run(
            self.noimage_instance, (self.start, None),
            no_image=True
        )
        # generate run for instance_2 with unknown image
        account_helper.generate_single_run(
            self.noimage_instance2, (self.start, None),
            no_image=True
        )
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # assert that we find instances but no images or RHEL/OCP instances.
        self.assertExpectedAccountOverview(overview, self.account,
                                           images=0, instances=2,
                                           rhel_instances=0,
                                           openshift_instances=0)

    def test_get_cloud_account_overview_account_creation_after(self):
        """Assert an overview of an account created after end reports None."""
        overview = reports.get_account_overview(
            self.account_after_end, self.start, self.end)
        self.assertExpectedAccountOverview(overview, self.account_after_end,
                                           images=None, instances=None,
                                           rhel_instances=None,
                                           openshift_instances=None,
                                           rhel_runtime_seconds=None,
                                           openshift_runtime_seconds=None,
                                           rhel_images_challenged=None,
                                           openshift_images_challenged=None,
                                           openshift_memory_seconds=None,
                                           openshift_vcpu_seconds=None,
                                           rhel_memory_seconds=None,
                                           rhel_vcpu_seconds=None)

    def test_get_cloud_account_overview_account_creation_on(self):
        """Assert an overview of an account created on end reports None."""
        overview = reports.get_account_overview(
            self.account_on_end, self.start, self.end)
        self.assertExpectedAccountOverview(overview, self.account_on_end,
                                           images=None, instances=None,
                                           rhel_instances=None,
                                           openshift_instances=None,
                                           rhel_runtime_seconds=None,
                                           openshift_runtime_seconds=None,
                                           rhel_images_challenged=None,
                                           openshift_images_challenged=None,
                                           openshift_memory_seconds=None,
                                           openshift_vcpu_seconds=None,
                                           rhel_memory_seconds=None,
                                           rhel_vcpu_seconds=None)

    def test_get_cloud_account_overview_future_start_end(self):
        """Assert an overview of an account created on end reports None."""
        overview = reports.get_account_overview(
            self.account, self.start_future, self.end_future)
        self.assertExpectedAccountOverview(overview, self.account,
                                           images=None, instances=None,
                                           rhel_instances=None,
                                           openshift_instances=None,
                                           rhel_runtime_seconds=None,
                                           openshift_runtime_seconds=None,
                                           rhel_images_challenged=None,
                                           openshift_images_challenged=None,
                                           openshift_memory_seconds=None,
                                           openshift_vcpu_seconds=None,
                                           rhel_memory_seconds=None,
                                           rhel_vcpu_seconds=None)

    def test_get_cloud_account_overview_instance_old_and_new_events(self):
        """
        Test an account with an instance with some old and new events.

        This test covers a buggy situation we found in production in which
        having an instance with its "instance type" or "image" events defined
        before the reporting period would result in missing data.

        In this test, only the first power-on event includes the image and
        instance type information. All subsequent events leave them empty.
        """
        events = []

        # we specifically want an instance type that has not-1 values for
        # memory and cpu so we can verify different numbers in the results.
        instance_type = 't2.large'
        memory = util_helper.SOME_EC2_INSTANCE_TYPES[instance_type]['memory']
        vcpu = util_helper.SOME_EC2_INSTANCE_TYPES[instance_type]['vcpu']

        # a long time ago before the reporting period...
        # only the FIRST event has the image and instance type info.
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2017, 12, 10, 0, 0, 0),
                InstanceEvent.TYPE.power_on,
                ec2_ami_id=self.rhel_image.ec2_ami_id,
                instance_type=instance_type,
            )
        )
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2017, 12, 11, 0, 0, 0),
                InstanceEvent.TYPE.power_off,
                no_image=True,
                no_instance_type=True,
                no_subnet=True,
            )
        )

        # and during the reporting period...
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2018, 1, 2, 0, 0, 0),
                InstanceEvent.TYPE.power_on,
                no_image=True,
                no_instance_type=True,
                no_subnet=True,
            )
        )
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2018, 1, 3, 0, 0, 0),
                InstanceEvent.TYPE.power_off,
                no_image=True,
                no_instance_type=True,
                no_subnet=True,
            )
        )

        account_helper.recalculate_runs_from_events(events)

        overview = reports.get_account_overview(
            self.account, self.start, self.end
        )
        expected_runtime_seconds = DAY
        expected_memory_seconds = expected_runtime_seconds * memory
        expected_vcpu_seconds = expected_runtime_seconds * vcpu
        self.assertExpectedAccountOverview(
            overview,
            self.account,
            images=1,
            instances=1,
            rhel_instances=1,
            openshift_instances=0,
            rhel_runtime_seconds=expected_runtime_seconds,
            openshift_runtime_seconds=0,
            rhel_images_challenged=0,
            openshift_images_challenged=0,
            openshift_memory_seconds=0,
            openshift_vcpu_seconds=0,
            rhel_memory_seconds=expected_memory_seconds,
            rhel_vcpu_seconds=expected_vcpu_seconds,
        )

    def test_get_cloud_account_overview_instance_old_and_new_events_2(self):
        """
        Test an account with an instance with some old and new events.

        This test is very similar to the preceding test
        (test_get_cloud_account_overview_instance_old_and_new_events), but
        where the previous test does include a final power-off event, this test
        does not.
        """
        events = []

        # we specifically want an instance type that has not-1 values for
        # memory and cpu so we can verify different numbers in the results.
        instance_type = 't2.large'
        memory = util_helper.SOME_EC2_INSTANCE_TYPES[instance_type]['memory']
        vcpu = util_helper.SOME_EC2_INSTANCE_TYPES[instance_type]['vcpu']

        # a long time ago before the reporting period...
        # only the FIRST event has the image and instance type info.
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2017, 12, 10, 0, 0, 0),
                InstanceEvent.TYPE.power_on,
                ec2_ami_id=self.rhel_image.ec2_ami_id,
                instance_type=instance_type,
            )
        )
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2017, 12, 11, 0, 0, 0),
                InstanceEvent.TYPE.power_off,
                no_image=True,
                no_instance_type=True,
                no_subnet=True,
            )
        )

        # and during the reporting period...
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2018, 1, 2, 0, 0, 0),
                InstanceEvent.TYPE.power_on,
                no_image=True,
                no_instance_type=True,
                no_subnet=True,
            )
        )

        account_helper.recalculate_runs_from_events(events)

        overview = reports.get_account_overview(
            self.account, self.start, self.end
        )
        expected_runtime_seconds = DAY * 30  # the remainder of the month
        expected_memory_seconds = expected_runtime_seconds * memory
        expected_vcpu_seconds = expected_runtime_seconds * vcpu
        self.assertExpectedAccountOverview(
            overview,
            self.account,
            images=1,
            instances=1,
            rhel_instances=1,
            openshift_instances=0,
            rhel_runtime_seconds=expected_runtime_seconds,
            openshift_runtime_seconds=0,
            rhel_images_challenged=0,
            openshift_images_challenged=0,
            openshift_memory_seconds=0,
            openshift_vcpu_seconds=0,
            rhel_memory_seconds=expected_memory_seconds,
            rhel_vcpu_seconds=expected_vcpu_seconds,
        )

    def test_get_cloud_account_overview_instance_old_and_new_events_3(self):
        """
        Test an account with an instance with some old and new events.

        This test is also very similar to the preceding two tests
        (test_get_cloud_account_overview_instance_old_and_new_events and
        test_get_cloud_account_overview_instance_old_and_new_events_2), but
        this test includes multiple events before the reporting period that
        have the extra image/instance/subnet info stored as well as multiple
        events before the reported period that do *not* have that info stored.
        """
        events = []

        # we specifically want an instance type that has not-1 values for
        # memory and cpu so we can verify different numbers in the results.
        instance_type = 't2.large'
        memory = util_helper.SOME_EC2_INSTANCE_TYPES[instance_type]['memory']
        vcpu = util_helper.SOME_EC2_INSTANCE_TYPES[instance_type]['vcpu']

        # a long time ago before the reporting period...
        # in the old times, all events had the image/instance/subnet info.
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2017, 12, 10, 0, 0, 0),
                InstanceEvent.TYPE.power_on,
                ec2_ami_id=self.rhel_image.ec2_ami_id,
                instance_type=instance_type,
            )
        )
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2017, 12, 11, 0, 0, 0),
                InstanceEvent.TYPE.power_off,
                ec2_ami_id=self.rhel_image.ec2_ami_id,
                instance_type=instance_type,
                subnet=events[0].subnet,
            )
        )

        # some time later, we stopped writing that info after the first event.
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2017, 12, 15, 0, 0, 0),
                InstanceEvent.TYPE.power_on,
                no_image=True,
                no_instance_type=True,
                no_subnet=True,
            )
        )
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2017, 12, 16, 0, 0, 0),
                InstanceEvent.TYPE.power_off,
                no_image=True,
                no_instance_type=True,
                no_subnet=True,
            )
        )

        # and during the reporting period...
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2018, 1, 2, 0, 0, 0),
                InstanceEvent.TYPE.power_on,
                no_image=True,
                no_instance_type=True,
                no_subnet=True,
            )
        )

        account_helper.recalculate_runs_from_events(events)

        overview = reports.get_account_overview(
            self.account, self.start, self.end
        )
        expected_runtime_seconds = DAY * 30  # the remainder of the month
        expected_memory_seconds = expected_runtime_seconds * memory
        expected_vcpu_seconds = expected_runtime_seconds * vcpu
        self.assertExpectedAccountOverview(
            overview,
            self.account,
            images=1,
            instances=1,
            rhel_instances=1,
            openshift_instances=0,
            rhel_runtime_seconds=expected_runtime_seconds,
            openshift_runtime_seconds=0,
            rhel_images_challenged=0,
            openshift_images_challenged=0,
            openshift_memory_seconds=0,
            openshift_vcpu_seconds=0,
            rhel_memory_seconds=expected_memory_seconds,
            rhel_vcpu_seconds=expected_vcpu_seconds,
        )


class GetImageOverviewsTestCase(ReportTestBase):
    """Test various uses of get_image_overviews."""

    def assertImageGeneralMetadata(self, result, image):
        """Assert the image's various general metadata are as expected."""
        self.assertEqual(image.cloud_image_id, result['cloud_image_id'])
        self.assertEqual(image.id, result['id'])
        self.assertEqual(image.is_cloud_access, result['is_cloud_access'])
        self.assertEqual(image.is_encrypted, result['is_encrypted'])
        self.assertEqual(image.is_marketplace, result['is_marketplace'])
        self.assertEqual(image.name, result['name'])
        self.assertEqual(image.status, result['status'])

    def assertImageProductFindings(self, result, rhel=False,
                                   rhel_challenged=False, rhel_detected=False,
                                   openshift=False, openshift_challenged=False,
                                   openshift_detected=False, instances_seen=0,
                                   runtime_seconds=0.0):
        """Assert the image's various product findings are as expected."""
        self.assertEqual(rhel, result['rhel'])
        self.assertEqual(rhel_challenged, result['rhel_challenged'])
        self.assertEqual(rhel_detected, result['rhel_detected'])
        self.assertEqual(openshift, result['openshift'])
        self.assertEqual(openshift_challenged, result['openshift_challenged'])
        self.assertEqual(openshift_detected, result['openshift_detected'])
        self.assertEqual(instances_seen, result['instances_seen'])
        self.assertEqual(runtime_seconds, result['runtime_seconds'])

    def test_with_active_instance_usage_times(self):
        """
        Assert usage for RHEL, OpenShift, and "plain" images in the period.

        In this test, there are three active images. All instances for the
        images run for the same five-hour period for convenience. Other tests
        assert the more interesting handling of complex time calculations.

        The RHEL image is used by two instances, resulting in 10 hours.
        The OpenShift and plain images are each used by one instance, resulting
        in 5 hours for each of them.
        """
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        rhel_instance_1 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        rhel_instance_2 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        self.generate_runs(powered_times, rhel_instance_1, self.image_rhel)
        self.generate_runs(powered_times, rhel_instance_2, self.image_rhel)
        self.generate_runs(
            powered_times, self.openshift_instance, self.image_ocp
        )
        self.generate_runs(
            powered_times, self.plain_instance, self.image_plain
        )

        results = reports.get_images_overviews(self.user_1.id, self.start,
                                               self.end, self.account_1.id)

        self.assertEqual(3, len(results['images']))
        rhel_image_result = [obj for obj in results['images']
                             if obj['id'] == self.image_rhel.id][0]

        self.assertImageGeneralMetadata(rhel_image_result, self.image_rhel)
        self.assertImageProductFindings(rhel_image_result,
                                        rhel=True, rhel_detected=True,
                                        instances_seen=2,
                                        runtime_seconds=HOURS_10)

        ocp_image_result = [obj for obj in results['images']
                            if obj['id'] == self.image_ocp.id][0]
        self.assertImageGeneralMetadata(ocp_image_result, self.image_ocp)
        self.assertImageProductFindings(ocp_image_result, openshift=True,
                                        openshift_detected=True,
                                        instances_seen=1,
                                        runtime_seconds=HOURS_5)

        plain_image_result = [obj for obj in results['images']
                              if obj['id'] == self.image_plain.id][0]
        self.assertImageGeneralMetadata(plain_image_result, self.image_plain)
        self.assertImageProductFindings(plain_image_result,
                                        instances_seen=1,
                                        runtime_seconds=HOURS_5)

    def test_with_no_active_instance_usage_times(self):
        """
        Assert appropriate response when no instance activity is seen.

        In this test, instances using RHEL, OCP, and plain images all have
        activity, but that activity was before the report query time period.
        So, the results should include none of them.
        """
        powered_times = (
            (
                util_helper.utc_dt(2017, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2017, 1, 10, 5, 0, 0)
            ),
        )
        rhel_instance_1 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        rhel_instance_2 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        self.generate_runs(powered_times, rhel_instance_1, self.image_rhel)
        self.generate_runs(powered_times, rhel_instance_2, self.image_rhel)
        self.generate_runs(
            powered_times, self.openshift_instance, self.image_ocp
        )
        self.generate_runs(
            powered_times, self.plain_instance, self.image_plain
        )

        results = reports.get_images_overviews(self.user_1.id, self.start,
                                               self.end, self.account_1.id)

        self.assertEqual(0, len(results['images']))

    def test_no_images_for_bogus_account_id(self):
        """
        Assert appropriate response when no account is found.

        This case generally should not happen when frontigrade is making
        requests, but in case another client crafts a request with an account
        id that does not belong to the user, we should return an empty list.
        """
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        rhel_instance_1 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        rhel_instance_2 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        self.generate_runs(powered_times, rhel_instance_1, self.image_rhel)
        self.generate_runs(powered_times, rhel_instance_2, self.image_rhel)
        self.generate_runs(
            powered_times, self.openshift_instance, self.image_ocp
        )
        self.generate_runs(
            powered_times, self.plain_instance, self.image_plain
        )

        bad_account_id = util_helper.generate_dummy_aws_account_id()

        results = reports.get_images_overviews(self.user_1.id, self.start,
                                               self.end, bad_account_id)

        self.assertEqual(0, len(results['images']))

    def test_no_images_for_future_start_time(self):
        """
        If start, end times are in the future, test that we return nothing.

        This case generally should not happen when frontigrade is making
        requests, but in case another client crafts a request with future
        start/end times, we should return an empty list.
        """
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        rhel_instance_1 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        rhel_instance_2 = account_helper.generate_aws_instance(
            account=self.account_1, image=self.image_rhel
        )
        self.generate_runs(powered_times, rhel_instance_1, self.image_rhel)
        self.generate_runs(powered_times, rhel_instance_2, self.image_rhel)
        self.generate_runs(
            powered_times, self.openshift_instance, self.image_ocp
        )
        self.generate_runs(
            powered_times, self.plain_instance, self.image_plain
        )

        # Report on January in the year 2525
        start_future = util_helper.utc_dt(2525, 1, 1, 0, 0, 0)
        end_future = util_helper.utc_dt(2525, 2, 1, 0, 0, 0)

        results = reports.get_images_overviews(self.user_1.id, start_future,
                                               end_future, self.account_1.id)
        self.assertEqual(0, len(results['images']))


class GenerateDailyPeriodsTestCase(TestCase):
    """Test cases around _generate_daily_periods."""

    def assertExpectedCountAndEnd(self, periods, count, end):
        """Assert periods were generated with correct count and final end."""
        self.assertEqual(len(periods), count)
        if count > 0:
            self.assertEqual(periods[-1][1], end)

    def test_one_day_perfect(self):
        """Test for one exact day."""
        input_start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        input_end = util_helper.utc_dt(2018, 1, 2, 0, 0, 0)
        expected_count = 1
        expected_end = input_end
        periods = reports._generate_daily_periods(input_start, input_end)
        self.assertExpectedCountAndEnd(periods, expected_count, expected_end)

    def test_two_days_perfect(self):
        """Test for two exact days."""
        input_start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        input_end = util_helper.utc_dt(2018, 1, 3, 0, 0, 0)
        expected_count = 2
        expected_end = input_end
        periods = reports._generate_daily_periods(input_start, input_end)
        self.assertExpectedCountAndEnd(periods, expected_count, expected_end)

    def test_one_day_from_less_than_one(self):
        """Test for one partial-day period."""
        input_start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        input_end = util_helper.utc_dt(2018, 1, 1, 12, 34, 56)
        expected_count = 1
        expected_end = input_end
        periods = reports._generate_daily_periods(input_start, input_end)
        self.assertExpectedCountAndEnd(periods, expected_count, expected_end)

    def test_two_days_from_one_and_half(self):
        """Test for one whole day and one partial."""
        input_start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        input_end = util_helper.utc_dt(2018, 1, 2, 12, 34, 56)
        expected_count = 2
        expected_end = input_end
        periods = reports._generate_daily_periods(input_start, input_end)
        self.assertExpectedCountAndEnd(periods, expected_count, expected_end)

    def test_no_days_backwards_inputs(self):
        """Test no periods when end is before start."""
        input_start = util_helper.utc_dt(2018, 1, 2, 0, 0, 0)
        input_end = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        expected_count = 0
        periods = reports._generate_daily_periods(input_start, input_end)
        self.assertExpectedCountAndEnd(periods, expected_count, None)
