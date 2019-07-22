"""Collection of tests for api.util.calculate_max_concurrent_usage."""
import datetime

from django.test import TestCase

from api.tests import helper as api_helper
from api.util import calculate_max_concurrent_usage
from util.tests import helper as util_helper


class CalculateMaxConcurrentUsageTest(TestCase):
    """Test cases for api.util.calculate_max_concurrent_usage."""

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

    def test_when_user_id_does_not_exist(self):
        """Test when the requested user ID does not exist."""
        request_date = datetime.date(2019, 5, 1)
        user_id = -1  # negative id should never exit
        expected_date = request_date

        results = calculate_max_concurrent_usage(
            request_date, user_id=user_id
        )
        self.assertMaxConcurrentUsage(results, expected_date, 0, 0, 0.0)

    def test_when_account_id_does_not_exist(self):
        """Test when the requested account ID does not exist."""
        request_date = datetime.date(2019, 5, 1)
        user_id = self.user1.id
        cloud_account_id = -1  # negative id should never exit
        expected_date = request_date

        results = calculate_max_concurrent_usage(
            request_date, user_id=user_id, cloud_account_id=cloud_account_id
        )
        self.assertMaxConcurrentUsage(results, expected_date, 0, 0, 0.0)
