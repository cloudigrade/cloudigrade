"""Collection of tests for tasks.run_inspection_cluster."""
from unittest.mock import MagicMock, Mock, patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from api import tasks
from api.models import MachineImage
from api.tests import helper as account_helper
from util.exceptions import AwsECSInstanceNotReady, AwsTooManyECSInstances
from util.tests import helper as util_helper


class RunInspectionClusterTest(TestCase):
    """Celery task 'run_inspection_cluster' test cases."""

    @patch('api.tasks.boto3')
    @patch('api.tasks.aws')
    def test_run_inspection_cluster_success(self, mock_aws, mock_boto3):
        """Asserts successful starting of the houndigrade task."""
        mock_ami_id = util_helper.generate_dummy_image_id()

        image = account_helper.generate_aws_image(
            ec2_ami_id=mock_ami_id, status=MachineImage.PENDING
        )

        mock_list_container_instances = {
            'containerInstanceArns': [util_helper.generate_dummy_instance_id()]
        }
        mock_ec2 = Mock()
        mock_ecs = MagicMock()

        mock_ecs.list_container_instances.return_value = (
            mock_list_container_instances
        )

        mock_boto3.client.return_value = mock_ecs
        mock_boto3.resource.return_value = mock_ec2

        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session.return_value = mock_session

        messages = [
            {
                'ami_id': mock_ami_id,
                'volume_id': util_helper.generate_dummy_volume_id(),
            }
        ]
        tasks.run_inspection_cluster(messages)

        image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.INSPECTING)

        mock_ecs.list_container_instances.assert_called_once_with(
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME
        )
        mock_ecs.describe_container_instances.assert_called_once_with(
            containerInstances=[
                mock_list_container_instances['containerInstanceArns'][0]
            ],
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
        )
        mock_ecs.register_task_definition.assert_called_once()
        mock_ecs.run_task.assert_called_once()

        mock_ec2.Volume.assert_called_once_with(messages[0]['volume_id'])
        mock_ec2.Volume.return_value.attach_to_instance.assert_called_once()

    @patch('api.models.AwsMachineImage.objects')
    @patch('api.tasks.boto3')
    def test_run_inspection_cluster_with_no_instances(
        self, mock_boto3, mock_machine_image_objects
    ):
        """Assert that an exception is raised if no instance is ready."""
        messages = [
            {
                'ami_id': util_helper.generate_dummy_image_id(),
                'volume_id': util_helper.generate_dummy_volume_id(),
            }
        ]
        mock_machine_image_objects.get.return_value = (
            mock_machine_image_objects
        )
        mock_list_container_instances = {'containerInstanceArns': []}
        mock_ecs = MagicMock()
        mock_ecs.list_container_instances.return_value = (
            mock_list_container_instances
        )

        mock_boto3.client.return_value = mock_ecs

        with self.assertRaises(AwsECSInstanceNotReady):
            tasks.run_inspection_cluster(messages)

    @patch('api.tasks.boto3')
    def test_run_inspection_cluster_with_no_known_images(self, mock_boto3):
        """Assert that inspection is skipped if no known images are given."""
        messages = [{'ami_id': util_helper.generate_dummy_image_id()}]
        tasks.run_inspection_cluster(messages)
        mock_boto3.client.assert_not_called()

    @patch('api.models.AwsMachineImage.objects')
    @patch('api.tasks.boto3')
    def test_run_inspection_cluster_with_too_many_instances(
        self, mock_boto3, mock_machine_image_objects
    ):
        """Assert that an exception is raised with too many instances."""
        messages = [
            {
                'ami_id': util_helper.generate_dummy_image_id(),
                'volume_id': util_helper.generate_dummy_volume_id(),
            }
        ]
        mock_machine_image_objects.get.return_value = (
            mock_machine_image_objects
        )
        mock_list_container_instances = {
            'containerInstanceArns': [
                util_helper.generate_dummy_instance_id(),
                util_helper.generate_dummy_instance_id(),
            ]
        }
        mock_ecs = MagicMock()
        mock_ecs.list_container_instances.return_value = (
            mock_list_container_instances
        )

        mock_boto3.client.return_value = mock_ecs

        with self.assertRaises(AwsTooManyECSInstances):
            tasks.run_inspection_cluster(messages)

    @patch('api.tasks.boto3')
    @patch('api.tasks.aws')
    def test_run_inspection_cluster_with_marketplace_volume(
        self, mock_aws, mock_boto3
    ):
        """Assert that ami is marked as inspected if marketplace volume."""
        mock_ami_id = util_helper.generate_dummy_image_id()

        image = account_helper.generate_aws_image(
            ec2_ami_id=mock_ami_id, status=MachineImage.PENDING
        )

        mock_list_container_instances = {
            'containerInstanceArns': [util_helper.generate_dummy_instance_id()]
        }
        mock_ec2 = Mock()
        mock_ecs = MagicMock()

        mock_volume = mock_ec2.Volume.return_value

        mock_volume.attach_to_instance.side_effect = ClientError(
            error_response={
                'Error': {
                    'Code': 'OptInRequired',
                    'Message': 'Marketplace Error',
                }
            },
            operation_name=Mock(),
        )

        mock_ecs.list_container_instances.return_value = (
            mock_list_container_instances
        )

        mock_boto3.client.return_value = mock_ecs
        mock_boto3.resource.return_value = mock_ec2

        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session.return_value = mock_session

        messages = [
            {
                'ami_id': mock_ami_id,
                'volume_id': util_helper.generate_dummy_volume_id(),
            }
        ]

        tasks.run_inspection_cluster(messages)
        image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.INSPECTED)

        mock_ecs.list_container_instances.assert_called_once_with(
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME
        )
        mock_ecs.describe_container_instances.assert_called_once_with(
            containerInstances=[
                mock_list_container_instances['containerInstanceArns'][0]
            ],
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
        )
        mock_ecs.register_task_definition.assert_not_called()
        mock_ecs.run_task.assert_not_called()

        mock_ec2.Volume.assert_called_once_with(messages[0]['volume_id'])
        mock_ec2.Volume.return_value.attach_to_instance.assert_called_once()

    @patch('api.tasks.boto3')
    @patch('api.tasks.aws')
    def test_run_inspection_cluster_with_unknown_error(
        self, mock_aws, mock_boto3
    ):
        """Assert that non marketplace errors are still raised."""
        mock_ami_id = util_helper.generate_dummy_image_id()

        image = account_helper.generate_aws_image(
            ec2_ami_id=mock_ami_id, status=MachineImage.PENDING
        )

        mock_list_container_instances = {
            'containerInstanceArns': [util_helper.generate_dummy_instance_id()]
        }
        mock_ec2 = Mock()
        mock_ecs = MagicMock()

        mock_volume = mock_ec2.Volume.return_value

        mock_volume.attach_to_instance.side_effect = ClientError(
            error_response={
                'Error': {'Code': 'ItIsAMystery', 'Message': 'Mystery Error'}
            },
            operation_name=Mock(),
        )

        mock_ecs.list_container_instances.return_value = (
            mock_list_container_instances
        )

        mock_boto3.client.return_value = mock_ecs
        mock_boto3.resource.return_value = mock_ec2

        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session.return_value = mock_session

        messages = [
            {
                'ami_id': mock_ami_id,
                'volume_id': util_helper.generate_dummy_volume_id(),
            }
        ]

        tasks.run_inspection_cluster(messages)
        image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.ERROR)

        mock_ecs.list_container_instances.assert_called_once_with(
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME
        )
        mock_ecs.describe_container_instances.assert_called_once_with(
            containerInstances=[
                mock_list_container_instances['containerInstanceArns'][0]
            ],
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
        )
        mock_ecs.register_task_definition.assert_not_called()
        mock_ecs.run_task.assert_not_called()

        mock_ec2.Volume.assert_called_once_with(messages[0]['volume_id'])
        mock_ec2.Volume.return_value.attach_to_instance.assert_called_once()
