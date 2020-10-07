"""Collection of tests for aws.tasks.cloudtrail.run_inspection_cluster."""
from unittest.mock import MagicMock, patch

from django.test import TestCase

from api.clouds.aws import tasks
from util.tests import helper as util_helper


class RunInspectionClusterTest(TestCase):
    """Celery task 'run_inspection_cluster' test cases."""

    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_run_inspection_cluster_success(self, mock_boto3):
        """Asserts successful starting of the houndigrade task."""
        ec2_instance_id = util_helper.generate_dummy_instance_id()
        ami_id_a = util_helper.generate_dummy_image_id()
        ami_id_b = util_helper.generate_dummy_image_id()
        ami_mountpoints = [
            (ami_id_a, "/dev/sdba"),
            (ami_id_b, "/dev/sdbb"),
        ]

        mock_ecs = MagicMock()
        mock_boto3.client.return_value = mock_ecs

        tasks.run_inspection_cluster(ec2_instance_id, ami_mountpoints)

        mock_ecs.register_task_definition.assert_called_once()
        mock_ecs.run_task.assert_called_once()
