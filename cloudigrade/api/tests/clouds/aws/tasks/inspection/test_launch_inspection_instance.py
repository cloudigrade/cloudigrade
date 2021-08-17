"""Collection of tests for aws.tasks.inspection.launch_inspection_instance."""
from unittest.mock import patch

from django.test import TestCase

from api.clouds.aws.tasks import launch_inspection_instance
from util.exceptions import SnapshotNotReadyException
from util.tests import helper as util_helper


class LaunchInspectionInstanceTest(TestCase):
    """Celery task 'launch_inspection_instance' test cases."""

    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_launch_inspection_instance(self, mock_boto3):
        """Assert that the launch_inspection_instance task succeeds."""
        mock_ami_id = util_helper.generate_dummy_image_id()
        mock_snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_ec2_client = mock_boto3.client
        mock_ec2_snapshot = mock_ec2_client.return_value.Snapshot
        mock_ec2_snapshot.return_value.state = "completed"
        mock_ec2_run_instances = mock_ec2_client.return_value.run_instances

        launch_inspection_instance(mock_ami_id, mock_snapshot_id)

        mock_ec2_client.assert_called_once_with("ec2")
        mock_ec2_run_instances.assert_called_once()

    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_launch_inspection_instance_snapshot_not_ready(self, mock_boto3):
        """Assert that the launch_inspection_instance task checks snapshot state."""
        mock_ami_id = util_helper.generate_dummy_image_id()
        mock_snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_ec2_client = mock_boto3.client
        mock_ec2_snapshot = mock_ec2_client.return_value.Snapshot
        mock_ec2_snapshot.return_value.snapshot_id = mock_snapshot_id
        mock_ec2_snapshot.return_value.state = "pending"
        mock_ec2_snapshot.return_value.progress = "69%"
        mock_ec2_run_instances = mock_ec2_client.return_value.run_instances

        with self.assertRaises(SnapshotNotReadyException):
            launch_inspection_instance(mock_ami_id, mock_snapshot_id)

        mock_ec2_client.assert_called_once_with("ec2")
        mock_ec2_run_instances.assert_not_called()
        mock_ec2_snapshot.assert_called_once_with(mock_snapshot_id)
