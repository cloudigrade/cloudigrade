"""Collection of tests for aws.tasks.inspection.launch_inspection_instance."""
from unittest.mock import patch

from django.test import TestCase

from api.clouds.aws.tasks import launch_inspection_instance
from api.models import MachineImage
from api.tests import helper as api_helper
from util.exceptions import SnapshotNotReadyException
from util.tests import helper as util_helper


class LaunchInspectionInstanceTest(TestCase):
    """Celery task 'launch_inspection_instance' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.mock_ami_id = util_helper.generate_dummy_image_id()
        self.mock_snapshot_id = util_helper.generate_dummy_snapshot_id()

        self.image1 = api_helper.generate_image(
            ec2_ami_id=self.mock_ami_id, status=MachineImage.PREPARING
        )

    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_launch_inspection_instance(self, mock_boto3):
        """Assert that the launch_inspection_instance task succeeds."""
        mock_ec2_client = mock_boto3.client
        mock_ec2_snapshot = mock_ec2_client.return_value.Snapshot
        mock_ec2_snapshot.return_value.state = "completed"
        mock_ec2_run_instances = mock_ec2_client.return_value.run_instances

        launch_inspection_instance(self.mock_ami_id, self.mock_snapshot_id)

        mock_ec2_client.assert_called_once_with("ec2")
        mock_ec2_run_instances.assert_called_once()

        self.image1.refresh_from_db()
        self.assertEqual(self.image1.status, MachineImage.INSPECTING)

    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_launch_inspection_instance_snapshot_not_ready(self, mock_boto3):
        """Assert that the launch_inspection_instance task checks snapshot state."""
        mock_ec2_client = mock_boto3.client
        mock_ec2_snapshot = mock_ec2_client.return_value.Snapshot
        mock_ec2_snapshot.return_value.snapshot_id = self.mock_snapshot_id
        mock_ec2_snapshot.return_value.state = "pending"
        mock_ec2_snapshot.return_value.progress = "69%"
        mock_ec2_run_instances = mock_ec2_client.return_value.run_instances

        with self.assertRaises(SnapshotNotReadyException):
            launch_inspection_instance(self.mock_ami_id, self.mock_snapshot_id)

        mock_ec2_client.assert_called_once_with("ec2")
        mock_ec2_run_instances.assert_not_called()
        mock_ec2_snapshot.assert_called_once_with(self.mock_snapshot_id)

        self.image1.refresh_from_db()
        self.assertEqual(self.image1.status, MachineImage.PREPARING)
