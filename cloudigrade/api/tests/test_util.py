"""Collection of tests for the api.util module."""
import datetime
import random
import uuid
from unittest.mock import Mock, patch

import faker
from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase
from rest_framework.serializers import ValidationError

import util.aws.sqs
from api import AWS_PROVIDER_STRING, util
from api.models import (AwsMachineImage, MachineImage,
                        MachineImageInspectionStart)
from api.tests import helper as api_helper
from api.util import calculate_max_concurrent_usage
from util import aws
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
        runs = util.normalize_runs(events)
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
        runs = util.normalize_runs(events)
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

        runs = util.normalize_runs(events)
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

        runs = util.normalize_runs(events)
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

        runs = util.normalize_runs(events)
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

        runs = util.normalize_runs(events)
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

        runs = util.normalize_runs(events)
        self.assertEquals(len(runs), 1)
        run = runs[0]
        self.assertEquals(run.start_time, powered_times[0][0])
        self.assertEquals(run.end_time, powered_times[0][1])
        self.assertEquals(run.instance_id, self.instance_plain.id)
        self.assertEquals(run.image_id, self.image_plain.id)


class CalculateMaxConcurrentUsageTest(TestCase):
    """Test cases for calculate_max_concurrent_usage."""

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
        """Assert expected calculate_max_concurrent_usage results."""
        self.assertEqual(results.date, date)
        self.assertEqual(results.instances, instances)
        self.assertEqual(results.vcpu, vcpu)
        self.assertEqual(results.memory, memory)

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

        results = calculate_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
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

        results = calculate_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
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

        results = calculate_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
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

        results = calculate_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
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

        results = calculate_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
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

        results = calculate_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
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

        results = calculate_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
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

        results = calculate_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
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

        results = calculate_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
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

        results = calculate_max_concurrent_usage(
            request_date,
            user_id=self.user1.id,
            cloud_account_id=self.user1account1.id,
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

        results = calculate_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
        self.assertMaxConcurrentUsage(
            results,
            expected_date,
            expected_instances,
            expected_vcpu,
            expected_memory,
        )


class AccountUtilTest(TestCase):
    """Account util test cases."""

    def test_create_new_machine_images(self):
        """Test that new machine images are saved to the DB."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        api_helper.generate_aws_account(arn=arn, aws_account_id=aws_account_id)

        region = util_helper.get_random_region()
        instances_data = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        ami_id = instances_data[region][0]['ImageId']

        mock_session = Mock()
        described_amis = util_helper.generate_dummy_describe_image(
            image_id=ami_id,
            owner_id=aws_account_id
        )

        with patch.object(util.aws, 'describe_images') as mock_describe_images:
            mock_describe_images.return_value = [described_amis]
            result = util.create_new_machine_images(mock_session,
                                                    instances_data)
            mock_describe_images.assert_called_with(mock_session, {ami_id},
                                                    region)

        self.assertEqual(result, [ami_id])

        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].ec2_ami_id, ami_id)

    def test_create_new_machine_images_with_windows_image(self):
        """Test that new windows machine images are marked appropriately."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        api_helper.generate_aws_account(arn=arn, aws_account_id=aws_account_id)

        region = util_helper.get_random_region()
        instances_data = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        instances_data[region][0]['Platform'] = 'Windows'
        ami_id = instances_data[region][0]['ImageId']

        mock_session = Mock()
        described_amis = util_helper.generate_dummy_describe_image(
            image_id=ami_id,
            owner_id=aws_account_id,
        )

        with patch.object(util.aws, 'describe_images') as mock_describe_images:
            mock_describe_images.return_value = [described_amis]
            result = util.create_new_machine_images(mock_session,
                                                    instances_data)
            mock_describe_images.assert_called_with(mock_session, {ami_id},
                                                    region)

        self.assertEqual(result, [ami_id])

        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].ec2_ami_id, ami_id)
        self.assertEqual(images[0].platform, AwsMachineImage.WINDOWS)

    def test_generate_aws_ami_messages(self):
        """Test that messages are formatted correctly."""
        region = util_helper.get_random_region()
        instance = util_helper.generate_dummy_describe_instance()
        instances_data = {region: [instance]}
        ami_list = [instance['ImageId']]

        expected = [{'cloud_provider': AWS_PROVIDER_STRING,
                     'region': region,
                     'image_id': instance['ImageId']}]

        result = util.generate_aws_ami_messages(instances_data, ami_list)

        self.assertEqual(result, expected)

    def test_sqs_wrap_message(self):
        """Test SQS message wrapping."""
        message_decoded = {'hello': 'world'}
        message_encoded = '{"hello": "world"}'
        with patch.object(util, 'uuid') as mock_uuid:
            wrapped_id = uuid.uuid4()
            mock_uuid.uuid4.return_value = wrapped_id
            actual_wrapped = util._sqs_wrap_message(message_decoded)
        self.assertEqual(actual_wrapped['Id'], str(wrapped_id))
        self.assertEqual(actual_wrapped['MessageBody'], message_encoded)

    def test_sqs_unwrap_message(self):
        """Test SQS message unwrapping."""
        message_decoded = {'hello': 'world'}
        message_encoded = '{"hello": "world"}'
        message_wrapped = {
            'Body': message_encoded,
        }
        actual_unwrapped = util._sqs_unwrap_message(message_wrapped)
        self.assertEqual(actual_unwrapped, message_decoded)

    def create_messages(self, count=1):
        """
        Create lists of messages for testing.

        Args:
            count (int): number of messages to generate

        Returns:
            tuple: Three lists. The first list contains the original message
                payloads. The second list contains the messages wrapped as we
                would batch send to SQS. The third list contains the messages
                wrapped as we would received from SQS.

        """
        payloads = []
        messages_sent = []
        messages_received = []
        for __ in range(count):
            message = f'Hello, {uuid.uuid4()}!'
            wrapped = util._sqs_wrap_message(message)
            payloads.append(message)
            messages_sent.append(wrapped)
            received = {
                'Id': wrapped['Id'],
                'Body': wrapped['MessageBody'],
                'ReceiptHandle': uuid.uuid4(),
            }
            messages_received.append(received)
        return payloads, messages_sent, messages_received

    @patch('api.util.boto3')
    @patch('api.util.aws.sqs.boto3')
    def test_add_messages_to_queue(self, mock_sqs_boto3, mock_boto3):
        """Test that messages get added to a message queue."""
        queue_name = 'Test Queue'
        messages, wrapped_messages, __ = self.create_messages()
        mock_sqs = mock_boto3.client.return_value
        mock_queue_url = Mock()
        mock_sqs_boto3.client.return_value.get_queue_url.return_value = {
            'QueueUrl': mock_queue_url
        }

        with patch.object(util, '_sqs_wrap_message') as mock_sqs_wrap_message:
            mock_sqs_wrap_message.return_value = wrapped_messages[0]
            util.add_messages_to_queue(queue_name, messages)
            mock_sqs_wrap_message.assert_called_once_with(messages[0])

        mock_sqs.send_message_batch.assert_called_with(
            QueueUrl=mock_queue_url, Entries=wrapped_messages
        )

    @patch('api.util.boto3')
    @patch('api.util.aws.sqs.boto3')
    def test_read_single_message_from_queue(self, mock_sqs_boto3, mock_boto3):
        """Test that messages are read from a message queue."""
        queue_name = 'Test Queue'
        actual_count = util.SQS_RECEIVE_BATCH_SIZE + 1
        requested_count = 1

        messages, __, wrapped_messages = self.create_messages(actual_count)
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[:requested_count]},
            {'Messages': []},
        ]
        read_messages = util.read_messages_from_queue(queue_name,
                                                      requested_count)
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch('api.util.boto3')
    @patch('api.util.aws.sqs.boto3')
    def test_read_messages_from_queue_until_empty(self, mock_sqs_boto3,
                                                  mock_boto3):
        """Test that all messages are read from a message queue."""
        queue_name = 'Test Queue'
        requested_count = util.SQS_RECEIVE_BATCH_SIZE + 1
        actual_count = util.SQS_RECEIVE_BATCH_SIZE - 1

        messages, __, wrapped_messages = self.create_messages(actual_count)
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[:util.SQS_RECEIVE_BATCH_SIZE]},
            {'Messages': []},
        ]
        read_messages = util.read_messages_from_queue(queue_name,
                                                      requested_count)
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch('api.util.boto3')
    @patch('api.util.aws.sqs.boto3')
    def test_read_messages_from_queue_stops_at_limit(self, mock_sqs_boto3,
                                                     mock_boto3):
        """Test that all messages are read from a message queue."""
        queue_name = 'Test Queue'
        requested_count = util.SQS_RECEIVE_BATCH_SIZE - 1
        actual_count = util.SQS_RECEIVE_BATCH_SIZE + 1

        messages, __, wrapped_messages = self.create_messages(actual_count)
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[:requested_count]},
            {'Messages': []},
        ]
        read_messages = util.read_messages_from_queue(queue_name,
                                                      requested_count)
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch('api.util.boto3')
    @patch('api.util.aws.sqs.boto3')
    def test_read_messages_from_queue_stops_has_error(self, mock_sqs_boto3,
                                                      mock_boto3):
        """Test we log if an error is raised when deleting from a queue."""
        queue_name = 'Test Queue'
        requested_count = util.SQS_RECEIVE_BATCH_SIZE - 1
        actual_count = util.SQS_RECEIVE_BATCH_SIZE + 1

        messages, __, wrapped_messages = self.create_messages(actual_count)
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[:requested_count]},
            {'Messages': []},
        ]
        error_response = {
            'Error': {
                'Code': 'it is a mystery'
            }
        }
        exception = ClientError(error_response, Mock())
        mock_sqs.delete_message.side_effect = exception
        read_messages = util.read_messages_from_queue(queue_name,
                                                      requested_count)
        self.assertEqual(set(read_messages), set())

    def test_convert_param_to_int_with_int(self):
        """Test that convert_param_to_int returns int with int."""
        result = util.convert_param_to_int('test_field', 42)
        self.assertEqual(result, 42)

    def test_convert_param_to_int_with_str_int(self):
        """Test that convert_param_to_int returns int with str int."""
        result = util.convert_param_to_int('test_field', '42')
        self.assertEqual(result, 42)

    def test_convert_param_to_int_with_str(self):
        """Test that convert_param_to_int returns int with str."""
        with self.assertRaises(ValidationError):
            util.convert_param_to_int('test_field', 'not_int')

    @patch('api.tasks.copy_ami_snapshot')
    def test_start_image_inspection_runs(self, mock_copy):
        """Test that inspection skips for marketplace images."""
        image = api_helper.generate_aws_image()
        mock_arn = Mock()
        mock_region = Mock()
        util.start_image_inspection(
            mock_arn, image.content_object.ec2_ami_id, mock_region)
        mock_copy.delay.assert_called_with(
            mock_arn,
            image.content_object.ec2_ami_id,
            mock_region)
        image.refresh_from_db()
        self.assertEqual(image.status, image.PREPARING)
        self.assertTrue(MachineImageInspectionStart.objects.filter(
            machineimage__id=image.id
        ).exists())

    @patch('api.tasks.copy_ami_snapshot')
    def test_start_image_inspection_marketplace_skips(self, mock_copy):
        """Test that inspection skips for marketplace images."""
        image = api_helper.generate_aws_image(is_marketplace=True)
        util.start_image_inspection(
            None, image.content_object.ec2_ami_id, None)
        mock_copy.delay.assert_not_called()
        image.refresh_from_db()
        self.assertEqual(image.status, image.INSPECTED)

    @patch('api.tasks.copy_ami_snapshot')
    def test_start_image_inspection_cloud_access_skips(self, mock_copy):
        """Test that inspection skips for Cloud Access images."""
        image = api_helper.generate_aws_image(is_cloud_access=True)
        util.start_image_inspection(
            None, image.content_object.ec2_ami_id, None)
        mock_copy.delay.assert_not_called()
        image.refresh_from_db()
        self.assertEqual(image.status, image.INSPECTED)

    @patch('api.tasks.copy_ami_snapshot')
    def test_start_image_inspection_exceed_max_allowed(self, mock_copy):
        """Test that inspection stops when max allowed attempts is exceeded."""
        image = api_helper.generate_aws_image()
        for _ in range(0, settings.MAX_ALLOWED_INSPECTION_ATTEMPTS + 1):
            MachineImageInspectionStart.objects.create(machineimage=image)
        util.start_image_inspection(
            None, image.content_object.ec2_ami_id, None)
        mock_copy.delay.assert_not_called()
        image.refresh_from_db()
        self.assertEqual(image.status, image.ERROR)

    def test_save_instance_with_unavailable_image(self):
        """Test that save instance events also writes image on instance."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        account = api_helper.generate_aws_account(
            arn=arn, aws_account_id=aws_account_id)

        region = util_helper.get_random_region()
        instances_data = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        ami_id = instances_data[region][0]['ImageId']

        awsinstance = util.save_instance(
            account, instances_data[region][0], region
        )
        instance = awsinstance.instance.get()

        self.assertEqual(instance.machine_image.content_object.ec2_ami_id,
                         ami_id)
        self.assertEqual(instance.machine_image.status,
                         MachineImage.UNAVAILABLE)

    def test_save_instance_with_missing_machineimage(self):
        """
        Test that save_instance works around a missing MachineImage.

        This is a use case that we *shouldn't* need, but until we identify how
        exactly AwsMachineImage objects are being saved without their matching
        MachineImage objects, we have this workaround to create the
        MachineImage at the time it is needed.
        """
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        account = api_helper.generate_aws_account(
            arn=arn, aws_account_id=aws_account_id
        )

        region = util_helper.get_random_region()
        instances_data = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        ami_id = instances_data[region][0]['ImageId']

        # Create the AwsMachineImage without its paired MachineImage.
        aws_machine_image = AwsMachineImage.objects.create(
            owner_aws_account_id=util_helper.generate_dummy_aws_account_id(),
            ec2_ami_id=ami_id,
            platform='none',
        )
        # Verify that the MachineImage was *not* created before proceeding.
        with self.assertRaises(MachineImage.DoesNotExist):
            aws_machine_image.machine_image.get()

        awsinstance = util.save_instance(
            account, instances_data[region][0], region
        )
        instance = awsinstance.instance.get()

        self.assertEqual(
            instance.machine_image.content_object.ec2_ami_id, ami_id
        )
        self.assertEqual(
            instance.machine_image.status, MachineImage.UNAVAILABLE
        )

    def test_save_instance_with_available_image(self):
        """Test that save instance events also writes image on instance."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        account = api_helper.generate_aws_account(
            arn=arn, aws_account_id=aws_account_id)

        region = util_helper.get_random_region()
        instances_data = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        ami_id = instances_data[region][0]['ImageId']

        mock_session = Mock()
        described_amis = util_helper.generate_dummy_describe_image(
            image_id=ami_id,
            owner_id=aws_account_id
        )

        with patch.object(util.aws, 'describe_images') as mock_describe_images:
            mock_describe_images.return_value = [described_amis]
            util.create_new_machine_images(mock_session, instances_data)
            mock_describe_images.assert_called_with(mock_session, {ami_id},
                                                    region)
        awsinstance = util.save_instance(
            account, instances_data[region][0], region
        )
        instance = awsinstance.instance.get()
        self.assertEqual(instance.machine_image.content_object.ec2_ami_id,
                         ami_id)
        self.assertEqual(instance.machine_image.status, MachineImage.PENDING)
