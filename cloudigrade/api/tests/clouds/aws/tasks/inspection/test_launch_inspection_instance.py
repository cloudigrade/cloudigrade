"""Collection of tests for aws.tasks.inspection.launch_inspection_instance."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
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
        mock_ec2_resource = mock_boto3.resource
        mock_ec2_snapshot = mock_ec2_resource.return_value.Snapshot
        mock_ec2_snapshot.return_value.state = "completed"

        mock_ec2_client = mock_boto3.client
        mock_ec2_run_instances = mock_ec2_client.return_value.run_instances

        launch_inspection_instance(self.mock_ami_id, self.mock_snapshot_id)

        mock_ec2_client.assert_called_once_with("ec2")
        mock_ec2_run_instances.assert_called_once()

        self.image1.refresh_from_db()
        self.assertEqual(self.image1.status, MachineImage.INSPECTING)

    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_launch_inspection_instance_snapshot_not_ready(self, mock_boto3):
        """Assert that the launch_inspection_instance task checks snapshot state."""
        mock_ec2_resource = mock_boto3.resource
        mock_ec2_snapshot = mock_ec2_resource.return_value.Snapshot
        mock_ec2_snapshot.return_value.snapshot_id = self.mock_snapshot_id
        mock_ec2_snapshot.return_value.state = "pending"
        mock_ec2_snapshot.return_value.progress = "69%"

        mock_ec2_client = mock_boto3.client
        mock_ec2_run_instances = mock_ec2_client.return_value.run_instances

        with self.assertRaises(SnapshotNotReadyException):
            launch_inspection_instance(self.mock_ami_id, self.mock_snapshot_id)

        mock_ec2_resource.assert_called_once_with("ec2")
        mock_ec2_client.assert_not_called()
        mock_ec2_run_instances.assert_not_called()
        mock_ec2_snapshot.assert_called_once_with(self.mock_snapshot_id)

        self.image1.refresh_from_db()
        self.assertEqual(self.image1.status, MachineImage.PREPARING)

    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_launch_inspection_instance_snapshot_not_known(self, mock_boto3):
        """Assert that the launch_inspection_instance exists early on unknown ami."""
        mock_ec2_resource = mock_boto3.resource
        mock_ec2_snapshot = mock_ec2_resource.return_value.Snapshot
        mock_ec2_snapshot.return_value.state = "completed"

        mock_ec2_client = mock_boto3.client
        mock_ec2_run_instances = mock_ec2_client.return_value.run_instances

        self.image1.delete()

        with self.assertLogs("api.clouds.aws.tasks.inspection", level="INFO") as logs:
            launch_inspection_instance(self.mock_ami_id, self.mock_snapshot_id)

        self.assertIn(self.mock_ami_id, logs.output[0])
        self.assertIn("no longer known to us", logs.output[0])
        mock_ec2_client.assert_not_called()
        mock_ec2_run_instances.assert_not_called()

    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_launch_inspection_instance_aws_marketplace_image(self, mock_boto3):
        """Assert that launch_inspection_instance exits early on marketplace error."""
        mock_ec2_resource = mock_boto3.resource
        mock_ec2_snapshot = mock_ec2_resource.return_value.Snapshot
        mock_ec2_snapshot.return_value.state = "completed"

        client_error = ClientError(
            error_response={
                "Error": {
                    "Code": "OptInRequired",
                    "Message": "In order to use this AWS Marketplace product you need "
                    "to accept terms and subscribe. To do so please visit "
                    "https://aws.amazon.com/marketplace/pp?",
                }
            },
            operation_name=Mock(),
        )

        mock_ec2_client = mock_boto3.client
        mock_ec2_run_instances = mock_ec2_client.return_value.run_instances
        mock_ec2_run_instances.side_effect = client_error

        with self.assertLogs("api.clouds.aws.tasks.inspection", level="INFO") as logs:
            launch_inspection_instance(self.mock_ami_id, self.mock_snapshot_id)

        mock_ec2_client.assert_called_once_with("ec2")
        mock_ec2_run_instances.assert_called_once()

        self.assertIn(self.mock_ami_id, logs.output[0])
        self.assertIn("appears to be an AWS Marketplace image", logs.output[1])

        self.image1.refresh_from_db()
        self.assertEqual(self.image1.status, MachineImage.INSPECTED)
        self.image1.content_object.refresh_from_db()
        self.assertTrue(self.image1.content_object.aws_marketplace_image)
