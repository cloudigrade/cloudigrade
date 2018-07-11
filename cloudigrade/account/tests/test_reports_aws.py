"""Collection of tests for the reports module."""

from django.test import TestCase

from account import AWS_PROVIDER_STRING, reports
from account.models import AwsAccount, InstanceEvent
from account.tests import helper as account_helper
from util.tests import helper as util_helper

HOUR = 60. * 60
DAY = HOUR * 24
HOURS_5 = HOUR * 5
HOURS_10 = HOUR * 10
HOURS_15 = HOUR * 15
DAYS_31 = DAY * 31


class GetTimeUsageAwsNoDataTest(TestCase):
    """_get_time_usage_aws test case for when no data exists."""

    def test_usage_no_account(self):
        """Assert exception raised when reporting on bogus account ID."""
        with self.assertRaises(AwsAccount.DoesNotExist):
            reports.get_time_usage(
                util_helper.utc_dt(2018, 1, 1, 0, 0, 0),
                util_helper.utc_dt(2018, 2, 1, 0, 0, 0),
                AWS_PROVIDER_STRING,
                util_helper.generate_dummy_aws_account_id(),
            )


class GetTimeUsageAwsTestMixin(object):
    """Mixin for common functions to use in GetTimeUsageAws*Test classes."""

    def generate_events_for_instance(self, powered_times, instance):
        """
        Generate events in the DB and return the first one's identifier.

        Args:
            powered_times (list[tuple]): Time periods instance is powered on.
            instance (AwsInstance): Which instance has the events.

        Returns:
            str: The first event's product_identifier.

        """
        events = account_helper.generate_aws_instance_events(
            instance, powered_times
        )
        return events[0].product_identifier

    def assertHourlyUsage(self, expected_totals):
        """
        Assert _get_time_usage_aws produces output matching expected totals.

        Note: this function is mixedCase to match Django TestCase style.

        Args:
            expected_totals (dict): the expected totals data struct
        """
        actual_results = reports.get_time_usage(
            self.start, self.end, AWS_PROVIDER_STRING,
            self.account.aws_account_id
        )
        self.assertEqual(actual_results, expected_totals)


class GetTimeUsageAws1a1iTest(TestCase, GetTimeUsageAwsTestMixin):
    """_get_time_usage_aws tests for 1 account with 1 instance."""

    def setUp(self):
        """Set up commonly used data for each test."""
        self.account = account_helper.generate_aws_account()
        self.instance = account_helper.generate_aws_instance(self.account)
        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)

    def generate_events(self, powered_times):
        """
        Generate events in the DB and return the first one's identifier.

        Args:
            powered_times (list[tuple]): Time periods instance is powered on.

        Returns:
            str: If any were created, the first event's product_identifier.

        """
        return super(GetTimeUsageAws1a1iTest, self)\
            .generate_events_for_instance(powered_times, self.instance)

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
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        identifier = self.generate_events(powered_times)
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
            (
                util_helper.utc_dt(2018, 1, 10, 1, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        identifier = self.generate_events(powered_times)
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
            (
                util_helper.utc_dt(2017, 1, 1, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 1, 5, 0, 0)
            ),
        )
        identifier = self.generate_events(powered_times)
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
        powered_times = ((util_helper.utc_dt(2018, 1, 31, 19, 0, 0), None),)
        identifier = self.generate_events(powered_times)
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
        powered_times = ((util_helper.utc_dt(2017, 1, 1), None),)
        identifier = self.generate_events(powered_times)
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
            (util_helper.utc_dt(2017, 1, 1), util_helper.utc_dt(2019, 1, 1)),
        )
        identifier = self.generate_events(powered_times)
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
        identifier = self.generate_events(powered_times)
        expected = {identifier: HOURS_15}
        self.assertHourlyUsage(expected)


class GetTimeUsageAws1a2iTest(TestCase, GetTimeUsageAwsTestMixin):
    """
    _get_time_usage_aws tests for 1 account with 2 similar instances.

    This simulates the case of one customer having two instances running the
    same version of RHEL using the same AMI in the same subnet of the same
    instance size.
    """

    def setUp(self):
        """Set up commonly used data for each test."""
        self.account = account_helper.generate_aws_account()
        self.instance_1 = account_helper.generate_aws_instance(self.account)
        self.instance_2 = account_helper.generate_aws_instance(self.account)
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
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        events = account_helper.generate_aws_instance_events(
            self.instance_1, powered_times
        )

        identifier = events[0].product_identifier
        ec2_ami_id = events[0].machineimage.ec2_ami_id
        instance_type = events[0].instance_type
        subnet = events[0].subnet

        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 20, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 20, 5, 0, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.instance_2,
            powered_times,
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
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        events = account_helper.generate_aws_instance_events(
            self.instance_1, powered_times
        )

        identifier = events[0].product_identifier
        ec2_ami_id = events[0].machineimage.ec2_ami_id
        instance_type = events[0].instance_type
        subnet = events[0].subnet

        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 2, 30, 0),
                util_helper.utc_dt(2018, 1, 10, 7, 30, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.instance_2,
            powered_times,
            ec2_ami_id=ec2_ami_id,
            instance_type=instance_type,
            subnet=subnet,
        )
        expected = {identifier: HOURS_10}
        self.assertHourlyUsage(expected)


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
            self.account,
            is_encrypted=False,
            is_windows=True,
        )
        self.rhel_image = account_helper.generate_aws_image(
            self.account,
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            is_rhel=True,
            is_openshift=False)
        self.openshift_image = account_helper.generate_aws_image(
            self.account,
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            is_rhel=False,
            is_openshift=True)
        self.openshift_and_rhel_image = account_helper.generate_aws_image(
            self.account,
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            is_rhel=True,
            is_openshift=True)
        self.instance_1 = account_helper.generate_aws_instance(self.account)
        self.instance_2 = account_helper.generate_aws_instance(self.account)

    def test_get_cloud_account_overview_no_events(self):
        """Assert an overview of an account with no events returns 0s."""
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        expected_overview = \
            {'id': self.account.aws_account_id,
             'user_id': self.account.user_id,
             'type': AWS_PROVIDER_STRING,
             'arn': self.account.account_arn,
             'creation_date': self.account.created_at,
             'name': self.account.name,
             'images': 0,
             'instances': 0,
             'rhel_instances': 0,
             'openshift_instances': 0}
        self.assertEqual(expected_overview, overview)

    def test_get_cloud_account_overview_with_events(self):
        """Assert an account overview reports instances/images correctly."""
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.instance_1, powered_times,
            self.windows_image.ec2_ami_id
        )
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        expected_overview = \
            {'id': self.account.aws_account_id,
             'user_id': self.account.user_id,
             'type': AWS_PROVIDER_STRING,
             'arn': self.account.account_arn,
             'creation_date': self.account.created_at,
             'name': self.account.name,
             'images': 1,
             'instances': 1,
             'rhel_instances': 0,
             'openshift_instances': 0}
        self.assertEqual(expected_overview, overview)

    def test_get_cloud_account_overview_with_rhel_image(self):
        """Assert an account overview with events reports rhel correctly."""
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.instance_1, powered_times,
            self.windows_image.ec2_ami_id
        )
        # in addition to instance_1's events, we are creating an event for
        # instance_2 with a rhel_image
        account_helper.generate_single_aws_instance_event(
            self.instance_2, self.start, InstanceEvent.TYPE.power_on,
            self.rhel_image.ec2_ami_id)
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # we expect to find 2 total images, 2 total instances and 1 rhel
        # instance
        expected_overview = \
            {'id': self.account.aws_account_id,
             'user_id': self.account.user_id,
             'type': AWS_PROVIDER_STRING,
             'arn': self.account.account_arn,
             'creation_date': self.account.created_at,
             'name': self.account.name,
             'images': 2,
             'instances': 2,
             'rhel_instances': 1,
             'openshift_instances': 0}
        self.assertEqual(expected_overview, overview)

    def test_get_cloud_account_overview_with_openshift_image(self):
        """Assert an account overview with events reports correctly."""
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.instance_1, powered_times,
            self.windows_image.ec2_ami_id
        )
        # in addition to instance_1's events, we are creating an event for
        # instance_2 with an openshift_image
        account_helper.generate_single_aws_instance_event(
            self.instance_2, self.start, InstanceEvent.TYPE.power_on,
            self.openshift_image.ec2_ami_id)
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # we expect to find 2 total images, 2 total instances and 1
        # openshift instance
        expected_overview = \
            {'id': self.account.aws_account_id,
             'user_id': self.account.user_id,
             'type': AWS_PROVIDER_STRING,
             'arn': self.account.account_arn,
             'creation_date': self.account.created_at,
             'name': self.account.name,
             'images': 2,
             'instances': 2,
             'rhel_instances': 0,
             'openshift_instances': 1}
        self.assertEqual(expected_overview, overview)

    def test_get_cloud_account_overview_with_openshift_and_rhel_image(self):
        """Assert an account overview reports openshift and rhel correctly."""
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.instance_1, powered_times,
            self.windows_image.ec2_ami_id
        )
        # in addition to instance_1's events, we are creating an event for
        # instance_2 with a rhel & openshift_image
        account_helper.generate_single_aws_instance_event(
            self.instance_2, self.start, InstanceEvent.TYPE.power_on,
            self.openshift_and_rhel_image.ec2_ami_id)
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # we expect to find 2 total images, 2 total instances, 1 rhel instance
        # and 1 openshift instance
        expected_overview = \
            {'id': self.account.aws_account_id,
             'user_id': self.account.user_id,
             'type': AWS_PROVIDER_STRING,
             'arn': self.account.account_arn,
             'creation_date': self.account.created_at,
             'name': self.account.name,
             'images': 2,
             'instances': 2,
             'rhel_instances': 1,
             'openshift_instances': 1}
        self.assertEqual(expected_overview, overview)

    def test_get_cloud_account_overview_with_two_instances_same_image(self):
        """Assert an account overview reports images correctly."""
        # generate event for instance_1 with the rhel/openshift image
        account_helper.generate_single_aws_instance_event(
            self.instance_1, self.start, InstanceEvent.TYPE.power_on,
            self.openshift_and_rhel_image.ec2_ami_id)
        # generate event for instance_2 with the rhel/openshift image
        account_helper.generate_single_aws_instance_event(
            self.instance_2, self.start, InstanceEvent.TYPE.power_on,
            self.openshift_and_rhel_image.ec2_ami_id)
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # assert that we only find the one image
        expected_overview = \
            {'id': self.account.aws_account_id,
             'user_id': self.account.user_id,
             'type': AWS_PROVIDER_STRING,
             'arn': self.account.account_arn,
             'creation_date': self.account.created_at,
             'name': self.account.name,
             'images': 1,
             'instances': 2,
             'rhel_instances': 1,
             'openshift_instances': 1}
        self.assertEqual(expected_overview, overview)

    def test_get_cloud_account_overview_with_rhel(self):
        """Assert an account overview reports rhel correctly."""
        # generate event for instance_1 with the rhel/openshift image
        account_helper.generate_single_aws_instance_event(
            self.instance_1, self.start, InstanceEvent.TYPE.power_on,
            self.openshift_and_rhel_image.ec2_ami_id)
        # generate event for instance_2 with the rhel image
        account_helper.generate_single_aws_instance_event(
            self.instance_2, self.start, InstanceEvent.TYPE.power_on,
            self.rhel_image.ec2_ami_id)
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # assert that we only find the two rhel images
        expected_overview = \
            {'id': self.account.aws_account_id,
             'user_id': self.account.user_id,
             'type': AWS_PROVIDER_STRING,
             'arn': self.account.account_arn,
             'creation_date': self.account.created_at,
             'name': self.account.name,
             'images': 2,
             'instances': 2,
             'rhel_instances': 2,
             'openshift_instances': 1}
        self.assertEqual(expected_overview, overview)

    def test_get_cloud_account_overview_with_openshift(self):
        """Assert an account overview reports openshift correctly."""
        # generate event for instance_1 with the rhel/openshift image
        account_helper.generate_single_aws_instance_event(
            self.instance_1, self.start, InstanceEvent.TYPE.power_on,
            self.openshift_and_rhel_image.ec2_ami_id)
        # generate event for instance_2 with the openshift image
        account_helper.generate_single_aws_instance_event(
            self.instance_2, self.start, InstanceEvent.TYPE.power_on,
            self.openshift_image.ec2_ami_id)
        overview = reports.get_account_overview(
            self.account, self.start, self.end)
        # assert that we only find the two openshift images
        expected_overview = \
            {'id': self.account.aws_account_id,
             'user_id': self.account.user_id,
             'type': AWS_PROVIDER_STRING,
             'arn': self.account.account_arn,
             'creation_date': self.account.created_at,
             'name': self.account.name,
             'images': 2,
             'instances': 2,
             'rhel_instances': 1,
             'openshift_instances': 2}
        self.assertEqual(expected_overview, overview)

    def test_get_cloud_account_overview_account_creation_after(self):
        """Assert an overview of an account created after end reports None."""
        overview = reports.get_account_overview(
            self.account_after_end, self.start, self.end)
        expected_overview = \
            {'id': self.account_after_end.aws_account_id,
             'user_id': self.account_after_end.user_id,
             'type': AWS_PROVIDER_STRING,
             'arn': self.account_after_end.account_arn,
             'creation_date': self.account_after_end.created_at,
             'name': self.account_after_end.name,
             'images': None,
             'instances': None,
             'rhel_instances': None,
             'openshift_instances': None}
        self.assertEqual(expected_overview, overview)

    def test_get_cloud_account_overview_account_creation_on(self):
        """Assert an overview of an account created on end reports None."""
        overview = reports.get_account_overview(
            self.account_on_end, self.start, self.end)
        expected_overview = \
            {'id': self.account_on_end.aws_account_id,
             'user_id': self.account_on_end.user_id,
             'type': AWS_PROVIDER_STRING,
             'arn': self.account_on_end.account_arn,
             'creation_date': self.account_on_end.created_at,
             'name': self.account_on_end.name,
             'images': None,
             'instances': None,
             'rhel_instances': None,
             'openshift_instances': None}
        self.assertEqual(expected_overview, overview)

    # the following tests are assuming that the events have been returned
    # from the _get_relevant_events() function which will only return events
    # during the specified time period **or** if no events exist during the
    # time period, the last event that occurred. Therefore, the validate method
    # makes sure that we ignore out the off events that occurred before start
    def test_validate_event_off_after_start(self):
        """Test that an off event after start is a valid event to inspect."""
        powered_time = util_helper.utc_dt(2018, 1, 10, 0, 0, 0)

        event = account_helper.generate_single_aws_instance_event(
            self.instance_1, powered_time, InstanceEvent.TYPE.power_off
        )
        is_valid = reports.validate_event(event, self.start)
        self.assertEqual(is_valid, True)

    def test_validate_event_on_after_start(self):
        """Test that an on event after start is a valid event to inspect."""
        powered_time = util_helper.utc_dt(2018, 1, 10, 0, 0, 0)

        event = account_helper.generate_single_aws_instance_event(
            self.instance_1, powered_time, InstanceEvent.TYPE.power_on
        )
        is_valid = reports.validate_event(event, self.start)
        self.assertEqual(is_valid, True)

    def test_validate_event_on_before_start(self):
        """Test that an on event before start is a valid event to inspect."""
        powered_time = util_helper.utc_dt(2017, 12, 10, 0, 0, 0)

        event = account_helper.generate_single_aws_instance_event(
            self.instance_1, powered_time, InstanceEvent.TYPE.power_on
        )
        is_valid = reports.validate_event(event, self.start)
        self.assertEqual(is_valid, True)

    def test_validate_event_off_before_start(self):
        """Test that an off event before start is not a valid event."""
        powered_time = util_helper.utc_dt(2017, 12, 10, 0, 0, 0)

        event = account_helper.generate_single_aws_instance_event(
            self.instance_1, powered_time, InstanceEvent.TYPE.power_off
        )
        is_valid = reports.validate_event(event, self.start)
        self.assertEqual(is_valid, False)


class GetDailyUsageTest(TestCase, GetTimeUsageAwsTestMixin):
    """Test get_time_usage with 1 account, 4 instances, and 4 images."""

    def setUp(self):
        """Set up commonly used data for each test."""
        self.account = account_helper.generate_aws_account()

        self.instance_1 = account_helper.generate_aws_instance(self.account)
        self.instance_2 = account_helper.generate_aws_instance(self.account)
        self.instance_3 = account_helper.generate_aws_instance(self.account)
        self.instance_4 = account_helper.generate_aws_instance(self.account)
        self.instance_5 = account_helper.generate_aws_instance(self.account)

        self.plain_image = account_helper.generate_aws_image(self.account)
        self.rhel_image = account_helper.generate_aws_image(
            self.account, is_rhel=True)
        self.openshift_image = account_helper.generate_aws_image(
            self.account, is_openshift=True)
        self.rhel_openshift_image = account_helper.generate_aws_image(
            self.account, is_rhel=True, is_openshift=True)

        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)

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
                util_helper.utc_dt(2018, 1, 2, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 6, 0, 0, 0)
            ),
            (
                util_helper.utc_dt(2018, 1, 12, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 14, 0, 0, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.instance_1,
            powered_times_1,
            ec2_ami_id=self.rhel_image.ec2_ami_id,
        )

        powered_times_2 = (
            (
                util_helper.utc_dt(2018, 1, 3, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
            ),
            (
                util_helper.utc_dt(2018, 1, 21, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 23, 0, 0, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.instance_2,
            powered_times_2,
            ec2_ami_id=self.rhel_image.ec2_ami_id,
        )

        powered_times_3 = (
            (
                util_helper.utc_dt(2018, 1, 3, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 8, 0, 0, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.instance_3,
            powered_times_3,
            ec2_ami_id=self.plain_image.ec2_ami_id,
        )

        powered_times_4 = (
            (
                util_helper.utc_dt(2018, 1, 19, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 22, 0, 0, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.instance_4,
            powered_times_4,
            ec2_ami_id=self.openshift_image.ec2_ami_id,
        )

        powered_times_5 = (
            (
                util_helper.utc_dt(2018, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0)
            ),
            (
                util_helper.utc_dt(2018, 1, 20, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 22, 0, 0, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.instance_5,
            powered_times_5,
            ec2_ami_id=self.rhel_openshift_image.ec2_ami_id,
        )

        results = reports.get_daily_usage(
            self.account.user_id,
            self.start,
            self.end,
        )

        self.assertEqual(len(results['daily_usage']), 31)
        self.assertEqual(results['instances_seen_with_rhel'], 3)
        self.assertEqual(results['instances_seen_with_openshift'], 2)

        ##########

        # grand total of rhel seconds should be 13 days worth of seconds.
        self.assertEqual(sum((
            day['rhel_runtime_seconds'] for day in results['daily_usage']
        )), DAY * 13)

        # grand total of openshift seconds should be 6 days worth of seconds.
        self.assertEqual(sum((
            day['openshift_runtime_seconds'] for day in results['daily_usage']
        )), DAY * 6)

        ##########

        # number of individual days in which we saw anything rhel is 10
        self.assertEqual(sum((
            1 for day in results['daily_usage']
            if day['rhel_instances'] > 0
        )), 10)

        # number of individual days in which we saw anything openshift is 4
        self.assertEqual(sum((
            1 for day in results['daily_usage']
            if day['openshift_instances'] > 0
        )), 4)

        ##########

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

        ##########

        # number of days in which we saw 1 openshift running all day is 2
        self.assertEqual(sum((
            1 for day in results['daily_usage']
            if day['openshift_runtime_seconds'] == DAY * 2
        )), 2)

        # number of days in which we saw 2 openshifts running all day is 2
        self.assertEqual(sum((
            1 for day in results['daily_usage']
            if day['openshift_runtime_seconds'] == DAY * 2
        )), 2)
