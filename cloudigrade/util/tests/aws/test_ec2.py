"""Collection of tests for ``util.aws.ec2`` module."""
import uuid
from unittest.mock import Mock, patch

from django.test import TestCase

from util.aws import ec2
from util.tests import helper


class UtilAwsEc2Test(TestCase):
    """AWS EC2 utility functions test case."""

    def test_describe_instances_everywhere(self):
        """
        Assert we get expected instances in a dict keyed by regions.

        The setup here is a little complicated, and it's important to
        understand what's going into it. The mock response from the client's
        `describe_instances` includes a Reservations list of **three** elements
        with different Instances in each. It is unclear to us how AWS divides
        Instances into Reservations; so, we must ensure in our tests that we
        are checking for Instances in potentially multiple Reservations.
        """
        mock_regions = [f"region-{uuid.uuid4()}"]
        mock_role = helper.generate_dummy_role()

        mock_session = Mock()
        mock_assume_role = mock_session.client.return_value.assume_role
        mock_assume_role.return_value = mock_role

        mock_running_instance_1 = helper.generate_dummy_describe_instance(
            state=ec2.InstanceState.running
        )
        mock_running_instance_2 = helper.generate_dummy_describe_instance(
            state=ec2.InstanceState.running
        )
        mock_stopped_instance_1 = helper.generate_dummy_describe_instance(
            state=ec2.InstanceState.stopped
        )
        mock_stopped_instance_2 = helper.generate_dummy_describe_instance(
            state=ec2.InstanceState.stopped
        )
        mock_terminated_instance_1 = helper.generate_dummy_describe_instance(
            state=ec2.InstanceState.terminated
        )
        mock_terminated_instance_2 = helper.generate_dummy_describe_instance(
            state=ec2.InstanceState.terminated
        )

        mock_described = {
            "Reservations": [
                {"Instances": [mock_running_instance_1, mock_stopped_instance_1]},
                {"Instances": [mock_terminated_instance_1, mock_running_instance_2]},
                {"Instances": [mock_stopped_instance_2, mock_terminated_instance_2]},
            ],
        }

        mock_client = mock_session.client.return_value
        mock_client.describe_instances.return_value = mock_described

        expected_found = {
            mock_regions[0]: [
                mock_running_instance_1,
                mock_stopped_instance_1,
                mock_running_instance_2,
                mock_stopped_instance_2,
            ]
        }

        with patch.object(ec2, "get_regions") as mock_get_regions:
            mock_get_regions.return_value = mock_regions
            actual_found = ec2.describe_instances_everywhere(mock_session)

        self.assertDictEqual(expected_found, actual_found)

    def test_describe_instances(self):
        """Assert that describe_instances returns a dict of instances data."""
        instance_ids = [
            helper.generate_dummy_instance_id(),
            helper.generate_dummy_instance_id(),
            helper.generate_dummy_instance_id(),
            helper.generate_dummy_instance_id(),
        ]
        individual_described_instances = [
            helper.generate_dummy_describe_instance(instance_id)
            for instance_id in instance_ids
        ]
        response = {
            "Reservations": [
                {
                    "Instances": individual_described_instances[:2],
                },
                {
                    "Instances": individual_described_instances[2:],
                },
            ],
        }

        mock_session = Mock()
        mock_client = mock_session.client.return_value
        mock_client.describe_instances.return_value = response

        region = helper.get_random_region()

        described_instances = ec2.describe_instances(mock_session, instance_ids, region)

        self.assertEqual(set(described_instances.keys()), set(instance_ids))
        for described_instance in individual_described_instances:
            self.assertIn(described_instance, described_instances.values())

    def test_is_windows_lowercase(self):
        """Test that an instance with Platform 'windows' is windows."""
        dummy_instance = helper.generate_dummy_describe_instance(platform="windows")
        self.assertTrue(ec2.is_windows(dummy_instance))

    def test_is_windows_with_unexpected_case(self):
        """Test that an instance with Platform 'WiNdOwS' is windows."""
        dummy_instance = helper.generate_dummy_describe_instance(platform="WiNdOwS")
        self.assertTrue(ec2.is_windows(dummy_instance))

    def test_is_windows_with_empty_platform(self):
        """Test that an instance with no Platform is not windows."""
        dummy_instance = helper.generate_dummy_describe_instance()
        self.assertFalse(ec2.is_windows(dummy_instance))

    def test_is_windows_with_other_platform(self):
        """Test that an instance with Platform 'other' is not windows."""
        dummy_instance = helper.generate_dummy_describe_instance(platform="other")
        self.assertFalse(ec2.is_windows(dummy_instance))
