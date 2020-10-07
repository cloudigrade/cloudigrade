"""Collection of tests for aws.tasks.cloudtrail.attach_volumes_to_cluster."""
from unittest.mock import MagicMock, Mock, patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from api.clouds.aws import tasks
from api.models import MachineImage
from api.tests import helper as account_helper
from util import misc
from util.exceptions import AwsECSInstanceNotReady, AwsTooManyECSInstances
from util.tests import helper as util_helper

EC2_INSTANCE_STATE_RUNNING = {"Code": 16, "Name": "Running"}
EC2_INSTANCE_STATE_STOPPED = {"Code": 80, "Name": "Stopped"}


class AttachVolumesToClusterTest(TestCase):
    """Celery task 'attach_volumes_to_cluster' test cases."""

    @patch("api.clouds.aws.tasks.inspection.run_inspection_cluster")
    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_attach_volumes_to_cluster_success(
        self, mock_boto3, mock_run_inspection_cluster
    ):
        """Asserts successful starting of the houndigrade task."""
        ami_id = util_helper.generate_dummy_image_id()
        volume_id = util_helper.generate_dummy_volume_id()
        device_name = misc.generate_device_name(0)
        expected_ami_mountpoints = [(ami_id, device_name)]

        image = account_helper.generate_image(
            ec2_ami_id=ami_id, status=MachineImage.PENDING
        )

        instance_id = util_helper.generate_dummy_instance_id()
        mock_list_container_instances = {"containerInstanceArns": [instance_id]}
        mock_ec2 = Mock()
        mock_ec2_instance = mock_ec2.Instance.return_value
        mock_ec2_instance.state = EC2_INSTANCE_STATE_RUNNING

        mock_ecs = MagicMock()
        mock_ecs.list_container_instances.return_value = mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs
        mock_boto3.resource.return_value = mock_ec2

        mock_ecs.describe_container_instances.return_value = {
            "containerInstances": [{"ec2InstanceId": instance_id}]
        }

        messages = [{"ami_id": ami_id, "volume_id": volume_id}]
        tasks.attach_volumes_to_cluster(messages)

        image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.INSPECTING)

        mock_ecs.list_container_instances.assert_called_once_with(
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME, status="ACTIVE"
        )
        mock_ecs.describe_container_instances.assert_called_once_with(
            containerInstances=[instance_id],
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
        )

        mock_ec2.Volume.assert_called_once_with(volume_id)
        mock_ec2.Volume.return_value.attach_to_instance.assert_called_once_with(
            Device=device_name, InstanceId=instance_id
        )

        mock_run_inspection_cluster.delay.assert_called_once_with(
            instance_id, expected_ami_mountpoints
        )

    @patch("api.clouds.aws.tasks.inspection.run_inspection_cluster")
    @patch("api.clouds.aws.models.AwsMachineImage.objects")
    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_attach_volumes_to_cluster_with_no_instances(
        self, mock_boto3, mock_machine_image_objects, mock_run_inspection_cluster
    ):
        """Assert that an exception is raised if no instance is ready."""
        messages = [
            {
                "ami_id": util_helper.generate_dummy_image_id(),
                "volume_id": util_helper.generate_dummy_volume_id(),
            }
        ]
        mock_machine_image_objects.get.return_value = mock_machine_image_objects
        mock_list_container_instances = {"containerInstanceArns": []}
        mock_ecs = MagicMock()
        mock_ecs.list_container_instances.return_value = mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs

        with self.assertRaises(AwsECSInstanceNotReady):
            tasks.attach_volumes_to_cluster(messages)

        mock_run_inspection_cluster.delay.assert_not_called()

    @patch("api.clouds.aws.tasks.inspection.run_inspection_cluster")
    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_attach_volumes_to_cluster_instance_not_running(
        self, mock_boto3, mock_run_inspection_cluster
    ):
        """Asserts that an exception is raised if instance exists but is not running."""
        ami_id = util_helper.generate_dummy_image_id()
        volume_id = util_helper.generate_dummy_volume_id()

        account_helper.generate_image(ec2_ami_id=ami_id, status=MachineImage.PENDING)

        instance_id = util_helper.generate_dummy_instance_id()
        mock_list_container_instances = {"containerInstanceArns": [instance_id]}
        mock_ec2 = Mock()
        mock_ec2_instance = mock_ec2.Instance.return_value
        mock_ec2_instance.state = EC2_INSTANCE_STATE_STOPPED

        mock_ecs = MagicMock()
        mock_ecs.list_container_instances.return_value = mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs
        mock_boto3.resource.return_value = mock_ec2

        messages = [{"ami_id": ami_id, "volume_id": volume_id}]
        with self.assertRaises(AwsECSInstanceNotReady):
            tasks.attach_volumes_to_cluster(messages)

        mock_run_inspection_cluster.delay.assert_not_called()

    @patch("api.clouds.aws.tasks.inspection.run_inspection_cluster")
    @patch("api.clouds.aws.tasks.inspection.scale_down_cluster")
    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_attach_volumes_to_cluster_with_no_known_images(
        self, mock_boto3, mock_scale_down, mock_run_inspection_cluster
    ):
        """Assert that inspection is skipped if no known images are given."""
        messages = [{"ami_id": util_helper.generate_dummy_image_id()}]
        tasks.attach_volumes_to_cluster(messages)
        mock_scale_down.delay.assert_called()
        mock_boto3.client.assert_not_called()
        mock_run_inspection_cluster.delay.assert_not_called()

    @patch("api.clouds.aws.tasks.inspection.run_inspection_cluster")
    @patch("api.clouds.aws.models.AwsMachineImage.objects")
    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_attach_volumes_to_cluster_with_too_many_instances(
        self, mock_boto3, mock_machine_image_objects, mock_run_inspection_cluster
    ):
        """Assert that an exception is raised with too many instances."""
        ami_id = util_helper.generate_dummy_image_id()
        volume_id = util_helper.generate_dummy_volume_id()

        instance_ids = [
            util_helper.generate_dummy_instance_id(),
            util_helper.generate_dummy_instance_id(),
        ]

        mock_machine_image_objects.get.return_value = mock_machine_image_objects
        mock_list_container_instances = {"containerInstanceArns": instance_ids}
        mock_ecs = MagicMock()
        mock_ecs.list_container_instances.return_value = mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs

        messages = [{"ami_id": ami_id, "volume_id": volume_id}]
        with self.assertRaises(AwsTooManyECSInstances):
            tasks.attach_volumes_to_cluster(messages)

        mock_run_inspection_cluster.delay.assert_not_called()

    @patch("api.clouds.aws.tasks.inspection.run_inspection_cluster")
    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_attach_volumes_to_cluster_with_marketplace_volume(
        self, mock_boto3, mock_run_inspection_cluster
    ):
        """Assert that ami is marked as inspected if marketplace volume."""
        ami_id = util_helper.generate_dummy_image_id()
        volume_id = util_helper.generate_dummy_volume_id()

        image = account_helper.generate_image(
            ec2_ami_id=ami_id, status=MachineImage.PENDING
        )

        instance_id = util_helper.generate_dummy_instance_id()
        mock_list_container_instances = {"containerInstanceArns": [instance_id]}
        mock_ec2 = Mock()
        mock_ec2_instance = mock_ec2.Instance.return_value
        mock_ec2_instance.state = EC2_INSTANCE_STATE_RUNNING

        mock_volume = mock_ec2.Volume.return_value
        mock_volume.attach_to_instance.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "OptInRequired",
                    "Message": "Marketplace Error",
                }
            },
            operation_name=Mock(),
        )

        mock_ecs = MagicMock()
        mock_ecs.list_container_instances.return_value = mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs
        mock_boto3.resource.return_value = mock_ec2

        messages = [{"ami_id": ami_id, "volume_id": volume_id}]
        tasks.attach_volumes_to_cluster(messages)
        image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.INSPECTED)

        mock_ecs.list_container_instances.assert_called_once_with(
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME, status="ACTIVE"
        )
        mock_ecs.describe_container_instances.assert_called_once_with(
            containerInstances=[instance_id],
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
        )
        mock_ecs.register_task_definition.assert_not_called()
        mock_ecs.run_task.assert_not_called()

        mock_ec2.Volume.assert_called_once_with(volume_id)
        mock_ec2.Volume.return_value.attach_to_instance.assert_called_once()

        mock_run_inspection_cluster.delay.assert_not_called()

    @patch("api.clouds.aws.tasks.inspection.run_inspection_cluster")
    @patch("api.clouds.aws.tasks.inspection.boto3")
    def test_attach_volumes_to_cluster_with_unknown_error(
        self, mock_boto3, mock_run_inspection_cluster
    ):
        """Assert that non marketplace errors are still raised."""
        ami_id = util_helper.generate_dummy_image_id()
        volume_id = util_helper.generate_dummy_volume_id()

        image = account_helper.generate_image(
            ec2_ami_id=ami_id, status=MachineImage.PENDING
        )

        instance_id = util_helper.generate_dummy_instance_id()
        mock_list_container_instances = {"containerInstanceArns": [instance_id]}
        mock_ec2 = Mock()
        mock_ec2_instance = mock_ec2.Instance.return_value
        mock_ec2_instance.state = EC2_INSTANCE_STATE_RUNNING

        mock_volume = mock_ec2.Volume.return_value
        mock_volume.attach_to_instance.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ItIsAMystery", "Message": "Mystery Error"}
            },
            operation_name=Mock(),
        )

        mock_ecs = MagicMock()
        mock_ecs.list_container_instances.return_value = mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs
        mock_boto3.resource.return_value = mock_ec2

        messages = [{"ami_id": ami_id, "volume_id": volume_id}]
        tasks.attach_volumes_to_cluster(messages)
        image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.ERROR)

        mock_ecs.list_container_instances.assert_called_once_with(
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME, status="ACTIVE"
        )
        mock_ecs.describe_container_instances.assert_called_once_with(
            containerInstances=[instance_id],
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
        )
        mock_ecs.register_task_definition.assert_not_called()
        mock_ecs.run_task.assert_not_called()

        mock_ec2.Volume.assert_called_once_with(volume_id)
        mock_ec2.Volume.return_value.attach_to_instance.assert_called_once()

        mock_run_inspection_cluster.delay.assert_not_called()
