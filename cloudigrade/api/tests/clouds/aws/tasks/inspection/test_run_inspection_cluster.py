"""Collection of tests for aws.tasks.cloudtrail.run_inspection_cluster."""
from unittest.mock import MagicMock, patch

from django.test import TestCase

from api.clouds.aws import tasks
from util.exceptions import AwsECSInstanceNotReady
from util.tests import helper as util_helper


class RunInspectionClusterTest(TestCase):
    """Celery task 'run_inspection_cluster' test cases."""

    def setUp(self):
        """Set up fixtures."""
        self.ec2_instance_id = util_helper.generate_dummy_instance_id()
        self.ami_id_a = util_helper.generate_dummy_image_id()
        self.ami_id_b = util_helper.generate_dummy_image_id()
        self.ami_id_c = util_helper.generate_dummy_image_id()
        self.ami_mountpoints = [
            (self.ami_id_a, "/dev/sdba"),
            (self.ami_id_b, "/dev/sdbb"),
            (self.ami_id_c, "/dev/sdbc"),
        ]

    @patch("api.clouds.aws.tasks.inspection._check_cluster_volume_mounts")
    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_run_inspection_cluster_success(
        self, mock_boto3, mock_check_cluster_volume_mounts
    ):
        """Assert successful starting of the houndigrade task."""
        mock_ecs = MagicMock()
        mock_boto3.client.return_value = mock_ecs
        mock_check_cluster_volume_mounts.return_value = True

        tasks.run_inspection_cluster(self.ec2_instance_id, self.ami_mountpoints)

        mock_check_cluster_volume_mounts.assert_called_once()
        mock_ecs.register_task_definition.assert_called_once()
        mock_ecs.run_task.assert_called_once()

    @patch("api.clouds.aws.tasks.inspection._check_cluster_volume_mounts")
    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_run_inspection_cluster_volume_mounts_not_ready(
        self, mock_boto3, mock_check_cluster_volume_mounts
    ):
        """Assert raising exception if volume mounts are not ready."""
        mock_ecs = MagicMock()
        mock_boto3.client.return_value = mock_ecs
        mock_check_cluster_volume_mounts.return_value = False

        with self.assertRaises(AwsECSInstanceNotReady):
            tasks.run_inspection_cluster(self.ec2_instance_id, self.ami_mountpoints)

        mock_check_cluster_volume_mounts.assert_called_once()
        mock_ecs.register_task_definition.assert_not_called()
        mock_ecs.run_task.assert_not_called()

    @patch("api.clouds.aws.tasks.inspection.describe_cluster_instances")
    def test_check_cluster_volume_mounts_success(self, mock_describe_cluster_instances):
        """Assert successfully checking the volume mounts are ready."""
        device_mappings = [
            util_helper.generate_dummy_block_device_mapping(
                device_name=self.ami_mountpoints[0][1]
            ),
            util_helper.generate_dummy_block_device_mapping(
                device_name=self.ami_mountpoints[1][1]
            ),
            util_helper.generate_dummy_block_device_mapping(
                device_name=self.ami_mountpoints[2][1]
            ),
        ]
        described_instances = {
            self.ec2_instance_id: util_helper.generate_dummy_describe_instance(
                instance_id=self.ec2_instance_id, device_mappings=device_mappings
            )
        }
        mock_describe_cluster_instances.return_value = described_instances

        volumes_mounted = tasks.inspection._check_cluster_volume_mounts(
            self.ec2_instance_id, self.ami_mountpoints
        )
        self.assertTrue(volumes_mounted)

    @patch("api.clouds.aws.tasks.inspection.describe_cluster_instances")
    def test_check_cluster_volume_mounts_not_ready(
        self, mock_describe_cluster_instances
    ):
        """Assert checking the volume mounts when they are not ready."""
        device_mappings = [
            util_helper.generate_dummy_block_device_mapping(
                device_name=self.ami_mountpoints[0][1], status="attaching"
            ),
            util_helper.generate_dummy_block_device_mapping(
                device_name=self.ami_mountpoints[1][1], status="suspicious"
            ),
        ]
        described_instances = {
            self.ec2_instance_id: util_helper.generate_dummy_describe_instance(
                instance_id=self.ec2_instance_id, device_mappings=device_mappings
            )
        }
        mock_describe_cluster_instances.return_value = described_instances

        with self.assertLogs(
            "api.clouds.aws.tasks.inspection", level="INFO"
        ) as logging_watcher:
            volumes_mounted = tasks.inspection._check_cluster_volume_mounts(
                self.ec2_instance_id, self.ami_mountpoints
            )

        self.assertFalse(volumes_mounted)
        self.assertEqual(len(logging_watcher.output), 3)
        self.assertIn("INFO", logging_watcher.output[0])
        self.assertIn("is still attaching", logging_watcher.output[0])
        self.assertIn("ERROR", logging_watcher.output[1])
        self.assertIn("has unexpected status", logging_watcher.output[1])
        self.assertIn("ERROR", logging_watcher.output[2])
        self.assertIn("not found in", logging_watcher.output[2])
