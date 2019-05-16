"""Collection of tests for the api.util module."""
import datetime
import random

import faker
from django.test import TestCase

from api.tests import helper as api_helper
from api.util import max_concurrent_usage, normalize_runs
from util.tests import helper as util_helper

_faker = faker.Faker()


class UtilNormalizeRunsTest(TestCase):
    """Test cases for runs calculations."""

    def setUp(self):
        """Set up commonly used data for each test."""
        # various images not belonging to any particular cloud account
        self.image_plain = api_helper.generate_aws_image()
        self.image_rhel = api_helper.generate_aws_image(rhel_detected=True)
        self.image_ocp = api_helper.generate_aws_image(openshift_detected=True)

        # define users
        self.user_1 = util_helper.generate_test_user()
        self.user_2 = util_helper.generate_test_user()
        self.user_super = util_helper.generate_test_user(is_superuser=True)

        # define users' cloud accounts
        self.account_1 = api_helper.generate_aws_account(
            user=self.user_1, name=_faker.bs()
        )

        # define instances that belong to user_1 account_1
        self.instance_plain = api_helper.generate_aws_instance(
            cloud_account=self.account_1, image=self.image_plain
        )
        self.instance_rhel = api_helper.generate_aws_instance(
            cloud_account=self.account_1, image=self.image_rhel
        )
        self.instance_ocp = api_helper.generate_aws_instance(
            cloud_account=self.account_1, image=self.image_ocp
        )
        self.instance_noimage = api_helper.generate_aws_instance(
            cloud_account=self.account_1, no_image=True
        )

        api_helper.generate_aws_ec2_definitions()

    def test_normalize_instance_on_off(self):
        """Test normalize_runs for one plain instance."""
        powered_times = (
            (
                util_helper.utc_dt(2019, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 10, 0, 0, 0),
            ),
        )
        events = api_helper.generate_aws_instance_events(
            self.instance_plain, powered_times
        )
        runs = normalize_runs(events)
        self.assertEquals(len(runs), 1)
        run = runs[0]
        self.assertEquals(run.start_time, powered_times[0][0])
        self.assertEquals(run.end_time, powered_times[0][1])
        self.assertEquals(run.instance_id, self.instance_plain.id)
        self.assertEquals(run.image_id, self.image_plain.id)

        # special flags
        self.assertFalse(run.is_cloud_access)
        self.assertFalse(run.is_encrypted)
        self.assertFalse(run.is_marketplace)

        # rhel detection
        self.assertFalse(run.rhel)
        self.assertFalse(run.rhel_detected)
        self.assertFalse(run.rhel_challenged)

        # openshift detection
        self.assertFalse(run.openshift)
        self.assertFalse(run.openshift_detected)
        self.assertFalse(run.openshift_challenged)

    def test_normalize_instance_on_never_off(self):
        """Test normalize_runs for an instance that starts but never stops."""
        powered_times = ((util_helper.utc_dt(2019, 1, 9, 0, 0, 0), None),)
        events = api_helper.generate_aws_instance_events(
            self.instance_plain, powered_times
        )
        runs = normalize_runs(events)
        self.assertEquals(len(runs), 1)
        run = runs[0]
        self.assertEquals(run.start_time, powered_times[0][0])
        self.assertEquals(run.end_time, powered_times[0][1])
        self.assertEquals(run.instance_id, self.instance_plain.id)
        self.assertEquals(run.image_id, self.image_plain.id)

    def test_normalize_multiple_instances_on_off(self):
        """Test normalize_runs for events for multiple instances and images."""
        rhel_powered_times = (
            (
                util_helper.utc_dt(2019, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 10, 0, 0, 0),
            ),
        )
        ocp_powered_times = (
            (
                util_helper.utc_dt(2019, 1, 8, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 11, 0, 0, 0),
            ),
        )
        rhel_events = api_helper.generate_aws_instance_events(
            self.instance_rhel, rhel_powered_times
        )
        ocp_events = api_helper.generate_aws_instance_events(
            self.instance_ocp, ocp_powered_times
        )

        # force some slight out-of-order shuffling of incoming events.
        events = rhel_events[:-1] + ocp_events[::-1] + rhel_events[-1:]
        random.shuffle(events)

        runs = normalize_runs(events)
        self.assertEquals(len(runs), 2)

        rhel_run = runs[0] if runs[0].rhel else runs[1]
        ocp_run = runs[0] if runs[0].openshift else runs[1]

        self.assertTrue(rhel_run.rhel)
        self.assertFalse(rhel_run.openshift)
        self.assertEquals(rhel_run.start_time, rhel_powered_times[0][0])
        self.assertEquals(rhel_run.end_time, rhel_powered_times[0][1])
        self.assertEquals(rhel_run.instance_id, self.instance_rhel.id)
        self.assertEquals(rhel_run.image_id, self.image_rhel.id)

        self.assertFalse(ocp_run.rhel)
        self.assertTrue(ocp_run.openshift)
        self.assertEquals(ocp_run.start_time, ocp_powered_times[0][0])
        self.assertEquals(ocp_run.end_time, ocp_powered_times[0][1])
        self.assertEquals(ocp_run.instance_id, self.instance_ocp.id)
        self.assertEquals(ocp_run.image_id, self.image_ocp.id)

    def test_normalize_one_instance_multiple_on_off(self):
        """Test normalize_runs one instance having multiple on-off cycles."""
        powered_times = (
            (
                util_helper.utc_dt(2019, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 10, 0, 0, 0),
            ),
            (
                util_helper.utc_dt(2019, 1, 11, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 12, 0, 0, 0),
            ),
            (util_helper.utc_dt(2019, 1, 13, 0, 0, 0), None),
        )
        events = api_helper.generate_aws_instance_events(
            self.instance_plain, powered_times
        )
        random.shuffle(events)

        runs = normalize_runs(events)
        self.assertEquals(len(runs), len(powered_times))
        sorted_runs = sorted(runs, key=lambda r: r.start_time)
        for index, run in enumerate(sorted_runs):
            self.assertEquals(run.start_time, powered_times[index][0])
            self.assertEquals(run.end_time, powered_times[index][1])
            self.assertEquals(run.instance_id, self.instance_plain.id)
            self.assertEquals(run.image_id, self.image_plain.id)

    def test_normalize_one_instance_on_on_on_off(self):
        """
        Test normalize_runs one instance with multiple on and one off.

        In this special case, only one run should be created. The first on
        event is the only one relevant to that run.
        """
        powered_times = (
            (util_helper.utc_dt(2019, 1, 9, 0, 0, 0), None),
            (util_helper.utc_dt(2019, 1, 11, 0, 0, 0), None),
            (
                util_helper.utc_dt(2019, 1, 13, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 14, 0, 0, 0),
            ),
        )
        events = api_helper.generate_aws_instance_events(
            self.instance_plain, powered_times
        )
        random.shuffle(events)

        runs = normalize_runs(events)
        self.assertEquals(len(runs), 1)
        run = runs[0]
        self.assertEquals(run.start_time, powered_times[0][0])
        self.assertEquals(run.end_time, powered_times[2][1])
        self.assertEquals(run.instance_id, self.instance_plain.id)
        self.assertEquals(run.image_id, self.image_plain.id)

    def test_normalize_one_instance_on_off_off_off(self):
        """
        Test normalize_runs one instance with multiple on and one off.

        In this special case, only one run should be created. The first off
        event is the only one relevant to that run.
        """
        powered_times = (
            (
                util_helper.utc_dt(2019, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 10, 0, 0, 0),
            ),
            (None, util_helper.utc_dt(2019, 1, 12, 0, 0, 0)),
            (None, util_helper.utc_dt(2019, 1, 14, 0, 0, 0)),
        )
        events = api_helper.generate_aws_instance_events(
            self.instance_plain, powered_times
        )
        random.shuffle(events)

        runs = normalize_runs(events)
        self.assertEquals(len(runs), 1)
        run = runs[0]
        self.assertEquals(run.start_time, powered_times[0][0])
        self.assertEquals(run.end_time, powered_times[0][1])
        self.assertEquals(run.instance_id, self.instance_plain.id)
        self.assertEquals(run.image_id, self.image_plain.id)

    def test_normalize_one_instance_on_on_off_off(self):
        """
        Test normalize_runs one instance with "overlapping" ons and offs.

        In this special case, the mock data simulates receiving information
        that would indicate two potentially overlapping runs. However, since
        we discard subsequent on and off events, we only generate one run.
        """
        powered_times = (
            (
                util_helper.utc_dt(2019, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 15, 0, 0, 0),
            ),
            (
                util_helper.utc_dt(2019, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 19, 0, 0, 0),
            ),
        )
        events = api_helper.generate_aws_instance_events(
            self.instance_plain, powered_times
        )
        random.shuffle(events)

        runs = normalize_runs(events)
        self.assertEquals(len(runs), 1)
        run = runs[0]
        self.assertEquals(run.start_time, powered_times[0][0])
        self.assertEquals(run.end_time, powered_times[0][1])
        self.assertEquals(run.instance_id, self.instance_plain.id)
        self.assertEquals(run.image_id, self.image_plain.id)


class MaxConcurrentUsageTest(TestCase):
    """Test cases for max_concurrent_usage."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user2 = util_helper.generate_test_user()
        self.superuser = util_helper.generate_test_user(is_superuser=True)

        self.user1account1 = api_helper.generate_aws_account(user=self.user1)
        self.user1account2 = api_helper.generate_aws_account(user=self.user1)
        self.user2account1 = api_helper.generate_aws_account(user=self.user2)

        self.image_rhel = api_helper.generate_aws_image(rhel_detected=True)
        self.image_plain = api_helper.generate_aws_image()

        self.instance_type_small = 't2.nano'  # 1 vcpu, 0.5 GB memory
        self.instance_type_small_specs = util_helper.SOME_EC2_INSTANCE_TYPES[
            self.instance_type_small
        ]

        self.instance_type_large = 'c5.xlarge'  # 4 vcpu, 8.0 GB memory
        self.instance_type_large_specs = util_helper.SOME_EC2_INSTANCE_TYPES[
            self.instance_type_large
        ]

    def assertMaxConcurrentUsage(self, results, date, instances, vcpu, memory):
        """Assert expected max_concurrent_usage results."""
        self.assertEqual(results['date'], date)
        self.assertEqual(results['instances'], instances)
        self.assertEqual(results['vcpu'], vcpu)
        self.assertEqual(results['memory'], memory)

    def test_single_rhel_run_within_day(self):
        """Test with a single RHEL instance run within the day."""
        rhel_instance = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
            instance_type=self.instance_type_large,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1
        expected_vcpu = self.instance_type_large_specs['vcpu']
        expected_memory = self.instance_type_large_specs['memory']

        results = max_concurrent_usage(request_date)
        self.assertMaxConcurrentUsage(
            results,
            expected_date,
            expected_instances,
            expected_vcpu,
            expected_memory,
        )

    def test_single_rhel_run_entirely_before_day(self):
        """Test with a RHEL instance run entirely before the day."""
        rhel_instance = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 4, 30, 1, 0, 0),
                util_helper.utc_dt(2019, 4, 30, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
            instance_type=self.instance_type_large,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date

        results = max_concurrent_usage(request_date)
        self.assertMaxConcurrentUsage(results, expected_date, 0, 0, 0)

    def test_single_rhel_run_entirely_after_day(self):
        """Test with a RHEL instance run entirely after the day."""
        rhel_instance = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 5, 2, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 2, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
            instance_type=self.instance_type_large,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date

        results = max_concurrent_usage(request_date)
        self.assertMaxConcurrentUsage(results, expected_date, 0, 0, 0)

    def test_single_run_overlapping_day_start(self):
        """Test with a RHEL instance run overlapping the start of the day."""
        rhel_instance = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 4, 30, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
            instance_type=self.instance_type_large,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1
        expected_vcpu = self.instance_type_large_specs['vcpu']
        expected_memory = self.instance_type_large_specs['memory']

        results = max_concurrent_usage(request_date)
        self.assertMaxConcurrentUsage(
            results,
            expected_date,
            expected_instances,
            expected_vcpu,
            expected_memory,
        )

    def test_single_run_overlapping_day_end(self):
        """Test with a RHEL instance run overlapping the end of the day."""
        rhel_instance = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 2, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
            instance_type=self.instance_type_large,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1
        expected_vcpu = self.instance_type_large_specs['vcpu']
        expected_memory = self.instance_type_large_specs['memory']

        results = max_concurrent_usage(request_date)
        self.assertMaxConcurrentUsage(
            results,
            expected_date,
            expected_instances,
            expected_vcpu,
            expected_memory,
        )

    def test_single_run_overlapping_day_entirely(self):
        """Test with a RHEL instance run overlapping the entire day."""
        rhel_instance = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 4, 30, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 2, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
            instance_type=self.instance_type_large,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1
        expected_vcpu = self.instance_type_large_specs['vcpu']
        expected_memory = self.instance_type_large_specs['memory']

        results = max_concurrent_usage(request_date)
        self.assertMaxConcurrentUsage(
            results,
            expected_date,
            expected_instances,
            expected_vcpu,
            expected_memory,
        )

    def test_single_not_rhel_run_within_day(self):
        """
        Test with a not-RHEL instance run within the day.

        This instance should have zero effect on max calculations.
        """
        rhel_instance = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_plain
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
            instance_type=self.instance_type_large,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date

        results = max_concurrent_usage(request_date)
        self.assertMaxConcurrentUsage(results, expected_date, 0, 0, 0)

    def test_overlapping_rhel_runs_within_day(self):
        """
        Test with two overlapping RHEL instances run within the day.

        Because no account filter is applied, both instances are seen.
        """
        rhel_instance1 = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        rhel_instance2 = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance1,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance1.machine_image,
            instance_type=self.instance_type_large,
        )
        api_helper.generate_single_run(
            rhel_instance2,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 30, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 30, 0),
            ),
            image=rhel_instance2.machine_image,
            instance_type=self.instance_type_small,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 2
        expected_vcpu = (
            self.instance_type_large_specs['vcpu'] +
            self.instance_type_small_specs['vcpu']
        )
        expected_memory = (
            self.instance_type_large_specs['memory'] +
            self.instance_type_small_specs['memory']
        )

        results = max_concurrent_usage(request_date)
        self.assertMaxConcurrentUsage(
            results,
            expected_date,
            expected_instances,
            expected_vcpu,
            expected_memory,
        )

    def test_overlapping_rhel_runs_within_day_with_user_filter(self):
        """
        Test with two overlapping RHEL instances run within the day.

        Because a user filter is applied, only one instance's data is seen.
        """
        rhel_instance1 = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        rhel_instance2 = api_helper.generate_aws_instance(
            self.user2account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance1,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance1.machine_image,
            instance_type=self.instance_type_large,
        )
        # This second instance run should be filtered away.
        api_helper.generate_single_run(
            rhel_instance2,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 30, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 30, 0),
            ),
            image=rhel_instance2.machine_image,
            instance_type=self.instance_type_small,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1
        expected_vcpu = self.instance_type_large_specs['vcpu']
        expected_memory = self.instance_type_large_specs['memory']

        results = max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(
            results,
            expected_date,
            expected_instances,
            expected_vcpu,
            expected_memory,
        )

    def test_overlapping_rhel_runs_within_day_with_account_filter(self):
        """
        Test with two overlapping RHEL instances run within the day.

        Because a account filter is applied, only one instance's data is seen.
        """
        rhel_instance1 = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        rhel_instance2 = api_helper.generate_aws_instance(
            self.user1account2, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance1,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0)
            ),
            image=rhel_instance1.machine_image,
            instance_type=self.instance_type_large,
        )
        # This second instance run should be filtered away.
        api_helper.generate_single_run(
            rhel_instance2,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 30, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 30, 0)
            ),
            image=rhel_instance2.machine_image,
            instance_type=self.instance_type_small,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1
        expected_vcpu = self.instance_type_large_specs['vcpu']
        expected_memory = self.instance_type_large_specs['memory']

        results = max_concurrent_usage(
            request_date, cloud_account_id=self.user1account1.id
        )
        self.assertMaxConcurrentUsage(
            results,
            expected_date,
            expected_instances,
            expected_vcpu,
            expected_memory,
        )

    def test_non_overlapping_rhel_runs_within_day(self):
        """
        Test with two non-overlapping RHEL instances run within the day.

        Two instances of different size run at different times, and this test
        should see the *larger* of the two matching the max values.
        """
        rhel_instance1 = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        rhel_instance2 = api_helper.generate_aws_instance(
            self.user1account2, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance1,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance1.machine_image,
            instance_type=self.instance_type_small,
        )
        api_helper.generate_single_run(
            rhel_instance2,
            (
                util_helper.utc_dt(2019, 5, 1, 3, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 4, 0, 0),
            ),
            image=rhel_instance2.machine_image,
            instance_type=self.instance_type_large,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1
        expected_vcpu = self.instance_type_large_specs['vcpu']
        expected_memory = self.instance_type_large_specs['memory']

        results = max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(
            results,
            expected_date,
            expected_instances,
            expected_vcpu,
            expected_memory,
        )
