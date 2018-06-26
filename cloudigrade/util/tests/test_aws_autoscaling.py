"""Collection of tests for ``util.aws.autoscaling`` module."""
import uuid
from unittest.mock import Mock, patch

from django.test import TestCase

from util.aws import autoscaling
from util.exceptions import AwsAutoScalingGroupNotFound


class UtilAwsAutoScalingTest(TestCase):
    """AWS Auto Scaling utility functions test case."""

    @patch('util.aws.autoscaling.boto3')
    def test_describe_auto_scaling_group(self, mock_boto3):
        """Assert successful fetch of auto scaling group description."""
        mock_group = Mock()
        groups = {
            'AutoScalingGroups': [mock_group]
        }
        client = mock_boto3.client.return_value
        client.describe_auto_scaling_groups.return_value = groups

        name = str(uuid.uuid4())
        described_group = autoscaling.describe_auto_scaling_group(name)
        self.assertEqual(described_group, mock_group)
        mock_boto3.client.assert_called_once_with('autoscaling')

    @patch('util.aws.autoscaling.boto3')
    def test_describe_auto_scaling_group_not_found(self, mock_boto3):
        """Assert getting group raises exception when not found."""
        groups = {
            'AutoScalingGroups': []
        }
        client = mock_boto3.client.return_value
        client.describe_auto_scaling_groups.return_value = groups

        name = str(uuid.uuid4())
        with self.assertRaises(AwsAutoScalingGroupNotFound):
            autoscaling.describe_auto_scaling_group(name)
        mock_boto3.client.assert_called_once_with('autoscaling')

    @patch('util.aws.autoscaling.describe_auto_scaling_group')
    def test_is_scaled_down(self, mock_describe):
        """Assert is_scaled_down is True when there are no instances."""
        mock_describe.return_value = {
            'MinSize': 0,
            'MaxSize': 0,
            'DesiredCapacity': 0,
            'Instances': [],
        }
        name = str(uuid.uuid4())
        scaled, _ = autoscaling.is_scaled_down(name)
        self.assertTrue(scaled)

    @patch('util.aws.autoscaling.describe_auto_scaling_group')
    def test_is_scaled_down_false_when_scaling_up(self, mock_describe):
        """Assert is_scaled_down is False when the cluster is scaling up."""
        mock_describe.return_value = {
            'MinSize': 1,
            'MaxSize': 1,
            'DesiredCapacity': 1,
            'Instances': [],
        }
        name = str(uuid.uuid4())
        scaled, _ = autoscaling.is_scaled_down(name)
        self.assertFalse(scaled)

    @patch('util.aws.autoscaling.describe_auto_scaling_group')
    def test_is_scaled_down_false_when_scaled_up(self, mock_describe):
        """Assert is_scaled_down is False when the cluster is scaled up."""
        mock_describe.return_value = {
            'MinSize': 1,
            'MaxSize': 1,
            'DesiredCapacity': 1,
            'Instances': [Mock()],
        }
        name = str(uuid.uuid4())
        scaled, _ = autoscaling.is_scaled_down(name)
        self.assertFalse(scaled)

    @patch('util.aws.autoscaling.describe_auto_scaling_group')
    def test_is_scaled_down_false_when_scaling_down(self, mock_describe):
        """Assert is_scaled_down is False when the cluster is scaling down."""
        mock_describe.return_value = {
            'MinSize': 0,
            'MaxSize': 0,
            'DesiredCapacity': 0,
            'Instances': [Mock()],
        }
        name = str(uuid.uuid4())
        scaled, _ = autoscaling.is_scaled_down(name)
        self.assertFalse(scaled)

    @patch('util.aws.autoscaling.boto3')
    def test_set_scale(self, mock_boto3):
        """Assert set_scale calls boto3 appropriately."""
        client = mock_boto3.client.return_value
        expected_response = client.update_auto_scaling_group.return_value

        name = str(uuid.uuid4())
        min_size = 1
        desired_capacity = 2
        max_size = 3

        actual_response = autoscaling.set_scale(
            name, min_size, max_size, desired_capacity
        )

        self.assertEqual(actual_response, expected_response)
        mock_boto3.client.assert_called_once_with('autoscaling')
        client.update_auto_scaling_group.assert_called_once_with(
            AutoScalingGroupName=name,
            MinSize=min_size,
            MaxSize=max_size,
            DesiredCapacity=desired_capacity
        )

    @patch('util.aws.autoscaling.set_scale')
    def test_scale_up(self, mock_set_scale):
        """Assert scale_up sets the scale to exactly 1."""
        name = str(uuid.uuid4())
        actual_response = autoscaling.scale_up(name)
        self.assertEqual(actual_response, mock_set_scale.return_value)
        mock_set_scale.assert_called_once_with(name, 1, 1, 1)

    @patch('util.aws.autoscaling.set_scale')
    def test_scale_down(self, mock_set_scale):
        """Assert scale_down sets the scale to exactly 0."""
        name = str(uuid.uuid4())
        actual_response = autoscaling.scale_down(name)
        self.assertEqual(actual_response, mock_set_scale.return_value)
        mock_set_scale.assert_called_once_with(name, 0, 0, 0)
