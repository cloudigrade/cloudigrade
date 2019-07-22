"""Collection of tests for api.util.get_max_concurrent_usage."""
import datetime

from django.test import TestCase

from api import tasks
from api.models import InstanceEvent
from api.tests import helper as api_helper
from api.util import get_max_concurrent_usage
from util.tests import helper as util_helper


class GetMaxConcurrentUsageTest(TestCase):
    """Test cases for api.util.get_max_concurrent_usage."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user1account1 = api_helper.generate_aws_account(user=self.user1)
        self.image_rhel = api_helper.generate_aws_image(rhel_detected=True)
        self.instance_type_large = 'c5.xlarge'  # 4 vcpu, 8.0 GB memory
        self.instance_type_large_specs = util_helper.SOME_EC2_INSTANCE_TYPES[
            self.instance_type_large
        ]
        api_helper.generate_aws_ec2_definitions()

    def assertMaxConcurrentUsage(self, results, date, instances, vcpu, memory):
        """Assert expected calculate_max_concurrent_usage results."""
        self.assertEqual(results.date, date)
        self.assertEqual(results.instances, instances)
        self.assertEqual(results.vcpu, vcpu)
        self.assertEqual(results.memory, memory)

    @util_helper.clouditardis(util_helper.utc_dt(2019, 5, 3, 0, 0, 0))
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

        results = get_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(
            results,
            expected_date,
            expected_instances,
            expected_vcpu,
            expected_memory,
        )

    @util_helper.clouditardis(util_helper.utc_dt(2019, 4, 24, 0, 0, 0))
    def test_get_usage_create_run_get_usage_again(self):
        """
        Test getting usage before and after creating a run.

        When we get usage for the first time, we typically save the calculated
        results, but if runs are created afterwards that would affect the
        usage, the saved data should have been deleted and recalculated for the
        subsequent request.
        """
        rhel_instance = api_helper.generate_aws_instance(
            self.user1account1, image=self.image_rhel
        )
        request_date = datetime.date(2019, 4, 22)
        expected_date = request_date
        results = get_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(results, expected_date, 0, 0, 0.0)

        # Simulate receiving a CloudTrail event for past instance power-on.
        occurred_at = util_helper.utc_dt(2019, 4, 20, 0, 0, 0)
        instance_event = api_helper.generate_single_aws_instance_event(
            instance=rhel_instance,
            occurred_at=occurred_at,
            event_type=InstanceEvent.TYPE.power_on,
            instance_type=self.instance_type_large,
        )
        tasks.process_instance_event(instance_event)

        expected_instances = 1
        expected_vcpu = self.instance_type_large_specs['vcpu']
        expected_memory = self.instance_type_large_specs['memory']

        results = get_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(
            results,
            expected_date,
            expected_instances,
            expected_vcpu,
            expected_memory,
        )
