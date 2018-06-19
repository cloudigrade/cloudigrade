"""Collection of tests for celery tasks."""
import json
import random
from unittest.mock import MagicMock, Mock, patch

from botocore.exceptions import ClientError
from celery.exceptions import Retry
from django.conf import settings
from django.test import TestCase

from account import tasks
from account.models import (AwsAccount,
                            AwsMachineImage,
                            ImageTag)
from account.tasks import (copy_ami_snapshot,
                           create_volume,
                           enqueue_ready_volume)
from util.exceptions import (AwsECSInstanceNotReady, AwsSnapshotCopyLimitError,
                             AwsSnapshotEncryptedError, AwsSnapshotError,
                             AwsSnapshotNotOwnedError, AwsTooManyECSInstances,
                             AwsVolumeError, AwsVolumeNotReadyError,
                             SnapshotNotReadyException)
from util.tests import helper as util_helper
from . import helper


class AccountCeleryTaskTest(TestCase):
    """Account app Celery task test cases."""

    def setUp(self):
        """Set up expected ready_volumes queue name."""
        self.ready_volumes_queue_name = '{0}ready_volumes'.format(
            settings.AWS_SQS_QUEUE_NAME_PREFIX
        )

    @patch('account.tasks.aws')
    def test_copy_ami_snapshot_success(self, mock_aws):
        """Assert that the snapshot copy task succeeds."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]['Ebs']['SnapshotId']
        mock_snapshot = util_helper.generate_mock_snapshot(mock_snapshot_id)
        mock_new_snapshot_id = util_helper.generate_dummy_snapshot_id()
        mock_session = mock_aws.boto3.Session.return_value

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot
        mock_aws.copy_snapshot.return_value = mock_new_snapshot_id

        with patch.object(tasks, 'create_volume') as mock_create_volume:
            copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            mock_create_volume.delay.assert_called_with(mock_image_id,
                                                        mock_new_snapshot_id)

        mock_aws.get_session.assert_called_with(mock_arn)
        mock_aws.get_ami.assert_called_with(
            mock_session,
            mock_image_id,
            mock_region
        )
        mock_aws.get_ami_snapshot_id.assert_called_with(mock_image)
        mock_aws.add_snapshot_ownership.assert_called_with(mock_snapshot)
        mock_aws.copy_snapshot.assert_called_with(
            mock_snapshot_id,
            mock_region
        )

    @patch('account.tasks.aws')
    def test_copy_ami_snapshot_encrypted(self, mock_aws):
        """Assert that the task marks the image as encrypted in the DB."""
        mock_account_id = util_helper.generate_dummy_aws_account_id()
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_arn = util_helper.generate_dummy_arn(mock_account_id, mock_region)

        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        mock_snapshot_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id,
            encrypted=True
        )
        mock_session = mock_aws.boto3.Session.return_value

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot

        account = AwsAccount(
            aws_account_id=mock_account_id,
            account_arn=mock_arn,
            user=util_helper.generate_test_user(),
        )
        account.save()
        ami = AwsMachineImage.objects.create(
            account=account,
            ec2_ami_id=mock_image_id
        )

        ami.save()

        with patch.object(tasks, 'create_volume') as mock_create_volume,\
                self.assertRaises(AwsSnapshotEncryptedError):
            copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            self.assertTrue(ami.is_encrypted)
            mock_create_volume.delay.assert_not_called()

    @patch('account.tasks.aws')
    def test_copy_ami_snapshot_retry_on_copy_limit(self, mock_aws):
        """Assert that the copy task is retried."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]['Ebs']['SnapshotId']
        mock_snapshot = util_helper.generate_mock_snapshot(mock_snapshot_id)
        mock_session = mock_aws.boto3.Session.return_value

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot
        mock_aws.add_snapshot_ownership.return_value = True
        mock_aws.copy_snapshot.side_effect = AwsSnapshotCopyLimitError()

        with patch.object(tasks, 'create_volume') as mock_create_volume,\
                patch.object(copy_ami_snapshot, 'retry') as mock_retry:
            mock_retry.side_effect = Retry()
            with self.assertRaises(Retry):
                copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            mock_create_volume.delay.assert_not_called()

    @patch('account.tasks.aws')
    def test_copy_ami_snapshot_retry_on_ownership_not_verified(self, mock_aws):
        """Assert that the snapshot copy task fails."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]['Ebs']['SnapshotId']
        mock_snapshot = util_helper.generate_mock_snapshot(mock_snapshot_id)
        mock_session = mock_aws.boto3.Session.return_value

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot
        mock_aws.add_snapshot_ownership.side_effect = \
            AwsSnapshotNotOwnedError()

        with patch.object(tasks, 'create_volume') as mock_create_volume,\
                patch.object(copy_ami_snapshot, 'retry') as mock_retry:
            mock_retry.side_effect = Retry()
            with self.assertRaises(Retry):
                copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            mock_create_volume.delay.assert_not_called()

    @patch('account.tasks.aws')
    def test_create_volume_success(self, mock_aws):
        """Assert that the volume create task succeeds."""
        ami_id = util_helper.generate_dummy_image_id()
        snapshot_id = util_helper.generate_dummy_snapshot_id()
        zone = settings.HOUNDIGRADE_AWS_AVAILABILITY_ZONE
        region = zone[:-1]

        mock_volume = util_helper.generate_mock_volume()
        mock_aws.create_volume.return_value = mock_volume.id
        mock_aws.get_region_from_availability_zone.return_value = region

        with patch.object(tasks, 'enqueue_ready_volume') as mock_enqueue:
            create_volume(ami_id, snapshot_id)
            mock_enqueue.delay.assert_called_with(
                ami_id,
                mock_volume.id,
                region
            )

        mock_aws.create_volume.assert_called_with(snapshot_id, zone)

    @patch('account.tasks.aws')
    def test_create_volume_retry_on_snapshot_not_ready(self, mock_aws):
        """Assert that the volume create task retries."""
        ami_id = util_helper.generate_dummy_image_id()
        snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_aws.create_volume.side_effect = SnapshotNotReadyException(
            snapshot_id
        )

        with patch.object(tasks, 'enqueue_ready_volume') as mock_enqueue,\
                patch.object(create_volume, 'retry') as mock_retry:
            mock_retry.side_effect = Retry()
            with self.assertRaises(Retry):
                create_volume(ami_id, snapshot_id)
            self.assertTrue(mock_retry.called)
            mock_enqueue.delay.assert_not_called()

    @patch('account.tasks.aws')
    def test_create_volume_abort_on_snapshot_error(self, mock_aws):
        """Assert that the volume create task does not retry on error."""
        ami_id = util_helper.generate_dummy_image_id()
        snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_aws.create_volume.side_effect = AwsSnapshotError()

        with patch.object(tasks, 'enqueue_ready_volume') as mock_enqueue,\
                patch.object(create_volume, 'retry') as mock_retry:
            mock_retry.side_effect = Retry()
            with self.assertRaises(AwsSnapshotError):
                create_volume(ami_id, snapshot_id)
            mock_retry.assert_not_called()
            mock_enqueue.delay.assert_not_called()

    @patch('account.tasks.add_messages_to_queue')
    @patch('account.tasks.aws')
    def test_enqueue_ready_volume_success(self, mock_aws, mock_queue):
        """Assert that volumes are enqueued when ready."""
        ami_id = util_helper.generate_dummy_image_id()
        volume_id = util_helper.generate_dummy_volume_id()
        mock_volume = util_helper.generate_mock_volume(
            volume_id=volume_id,
            state='available'
        )
        region = mock_volume.zone[:-1]

        mock_aws.get_volume.return_value = mock_volume
        messages = [{'ami_id': ami_id, 'volume_id': volume_id}]

        enqueue_ready_volume(ami_id, volume_id, region)

        mock_queue.assert_called_with(self.ready_volumes_queue_name, messages)

    @patch('account.tasks.aws')
    def test_enqueue_ready_volume_error(self, mock_aws):
        """Assert that an error is raised on bad volume state."""
        ami_id = util_helper.generate_dummy_image_id()
        volume_id = util_helper.generate_dummy_volume_id()
        mock_volume = util_helper.generate_mock_volume(
            volume_id=volume_id,
            state=random.choice(('in-use', 'deleting', 'deleted', 'error'))
        )
        region = mock_volume.zone[:-1]

        mock_aws.get_volume.return_value = mock_volume
        mock_aws.check_volume_state.side_effect = AwsVolumeError()

        with self.assertRaises(AwsVolumeError):
            enqueue_ready_volume(ami_id, volume_id, region)

    @patch('account.tasks.aws')
    def test_enqueue_ready_volume_retry(self, mock_aws):
        """Assert that the task retries when volume is not available."""
        ami_id = util_helper.generate_dummy_image_id()
        volume_id = util_helper.generate_dummy_volume_id()
        mock_volume = util_helper.generate_mock_volume(
            volume_id=volume_id,
            state='creating'
        )
        region = mock_volume.zone[:-1]

        mock_aws.get_volume.return_value = mock_volume
        mock_aws.check_volume_state.side_effect = AwsVolumeNotReadyError()

        with patch.object(enqueue_ready_volume, 'retry') as mock_retry:
            mock_retry.side_effect = Retry()
            with self.assertRaises(Retry):
                enqueue_ready_volume(ami_id, volume_id, region)

    @patch('account.tasks.add_messages_to_queue')
    @patch('account.tasks.run_inspection_cluster')
    @patch('account.tasks.read_messages_from_queue')
    @patch('account.tasks.aws')
    def test_scale_up_inspection_cluster_success(
            self,
            mock_aws,
            mock_read_messages_from_queue,
            mock_run_inspection_cluster,
            mock_add_messages_to_queue
    ):
        """Assert successful scaling with empty cluster and queued messages."""
        messages = [Mock()]
        mock_aws.is_scaled_down.return_value = True, dict()
        mock_read_messages_from_queue.return_value = messages

        tasks.scale_up_inspection_cluster()

        mock_aws.is_scaled_down.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_read_messages_from_queue.assert_called_once_with(
            self.ready_volumes_queue_name,
            settings.HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE
        )
        mock_aws.scale_up.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_run_inspection_cluster.delay.assert_called_once_with(messages)
        mock_add_messages_to_queue.assert_not_called()

    @patch('account.tasks.add_messages_to_queue')
    @patch('account.tasks.run_inspection_cluster')
    @patch('account.tasks.read_messages_from_queue')
    @patch('account.tasks.aws')
    def test_scale_up_inspection_cluster_aborts_when_not_scaled_down(
            self,
            mock_aws,
            mock_read_messages_from_queue,
            mock_run_inspection_cluster,
            mock_add_messages_to_queue
    ):
        """Assert scale up aborts when not scaled down."""
        mock_aws.is_scaled_down.return_value = False, {'Instances': [Mock()]}

        tasks.scale_up_inspection_cluster()

        mock_aws.is_scaled_down.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_aws.scale_up.assert_not_called()
        mock_read_messages_from_queue.assert_not_called()
        mock_run_inspection_cluster.delay.assert_not_called()
        mock_add_messages_to_queue.assert_not_called()

    @patch('account.tasks.add_messages_to_queue')
    @patch('account.tasks.run_inspection_cluster')
    @patch('account.tasks.read_messages_from_queue')
    @patch('account.tasks.aws')
    def test_scale_up_inspection_cluster_aborts_when_no_messages(
            self,
            mock_aws,
            mock_read_messages_from_queue,
            mock_run_inspection_cluster,
            mock_add_messages_to_queue
    ):
        """Assert scale up aborts when not scaled down."""
        mock_aws.is_scaled_down.return_value = True, dict()
        mock_read_messages_from_queue.return_value = []

        tasks.scale_up_inspection_cluster()

        mock_aws.is_scaled_down.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_aws.scale_up.assert_not_called()
        mock_read_messages_from_queue.assert_called_once_with(
            self.ready_volumes_queue_name,
            settings.HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE
        )
        mock_run_inspection_cluster.delay.assert_not_called()
        mock_add_messages_to_queue.assert_not_called()

    @patch('account.tasks.add_messages_to_queue')
    @patch('account.tasks.run_inspection_cluster')
    @patch('account.tasks.read_messages_from_queue')
    @patch('account.tasks.aws')
    def test_scale_up_inspection_cluster_requeues_on_aws_error(
            self,
            mock_aws,
            mock_read_messages_from_queue,
            mock_run_inspection_cluster,
            mock_add_messages_to_queue
    ):
        """Assert messages requeue when scale_up encounters AWS exception."""
        messages = [Mock()]
        mock_aws.is_scaled_down.return_value = True, dict()
        mock_read_messages_from_queue.return_value = messages
        mock_aws.scale_up.side_effect = ClientError({}, Mock())

        with self.assertRaises(RuntimeError):
            tasks.scale_up_inspection_cluster()

        mock_aws.is_scaled_down.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_aws.scale_up.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_add_messages_to_queue.assert_called_once_with(
            self.ready_volumes_queue_name,
            messages
        )
        mock_run_inspection_cluster.delay.assert_not_called()

    @patch('account.models.MachineImage.objects')
    @patch('account.tasks.boto3')
    def test_run_inspection_cluster_success(self, mock_boto3,
                                            mock_machine_image_objects):
        """Asserts successful starting of the houndigrade task."""
        mock_machine_image_objects.get.return_value = \
            mock_machine_image_objects

        mock_machine_image_objects.INSPECTING.return_value = 'inspecting'

        mock_list_container_instances = {
            'containerInstanceArns': [util_helper.generate_dummy_instance_id()]
        }
        mock_ec2 = Mock()
        mock_ecs = MagicMock()

        mock_ecs.list_container_instances.return_value = \
            mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs
        mock_boto3.resource.return_value = mock_ec2

        mock_ami_id = util_helper.generate_dummy_image_id()

        messages = [{'ami_id': mock_ami_id,
                     'volume_id': util_helper.generate_dummy_volume_id()}]
        tasks.run_inspection_cluster(messages)

        mock_machine_image_objects.get.assert_called_once_with(
            ec2_ami_id=mock_ami_id)

        self.assertEqual(mock_machine_image_objects.status.return_value,
                         mock_machine_image_objects.INSPECTING.return_value)

        mock_ecs.list_container_instances.assert_called_once_with(
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME)
        mock_ecs.describe_container_instances.assert_called_once_with(
            containerInstances=[
                mock_list_container_instances['containerInstanceArns'][0]],
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME
        )
        mock_ecs.register_task_definition.assert_called_once()
        mock_ecs.run_task.assert_called_once()

        mock_ec2.Volume.assert_called_once_with(messages[0]['volume_id'])
        mock_ec2.Volume.return_value.attach_to_instance.assert_called_once()

    @patch('account.models.MachineImage.objects')
    @patch('account.tasks.boto3')
    def test_run_inspection_cluster_with_no_instances(
            self, mock_boto3, mock_machine_image_objects):
        """Assert that an exception is raised if no instance is ready."""
        messages = [{'ami_id': util_helper.generate_dummy_image_id(),
                     'volume_id': util_helper.generate_dummy_volume_id()}]
        mock_machine_image_objects.get.return_value = \
            mock_machine_image_objects
        mock_list_container_instances = {'containerInstanceArns': []}
        mock_ecs = MagicMock()
        mock_ecs.list_container_instances.return_value = \
            mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs

        with self.assertRaises(AwsECSInstanceNotReady):
            tasks.run_inspection_cluster(messages)

    @patch('account.models.MachineImage.objects')
    @patch('account.tasks.boto3')
    def test_run_inspection_cluster_with_too_many_instances(
            self, mock_boto3, mock_machine_image_objects):
        """Assert that an exception is raised with too many instances."""
        messages = [{'ami_id': util_helper.generate_dummy_image_id(),
                     'volume_id': util_helper.generate_dummy_volume_id()}]
        mock_machine_image_objects.get.return_value = \
            mock_machine_image_objects
        mock_list_container_instances = {
            'containerInstanceArns': [
                util_helper.generate_dummy_instance_id(),
                util_helper.generate_dummy_instance_id()
            ]
        }
        mock_ecs = MagicMock()
        mock_ecs.list_container_instances.return_value = \
            mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs

        with self.assertRaises(AwsTooManyECSInstances):
            tasks.run_inspection_cluster(messages)

    @patch('account.tasks.persist_aws_inspection_cluster_results')
    @patch('account.tasks.read_messages_from_queue')
    def test_persist_inspect_results_no_messages(
            self,
            mock_read_messages_from_queue,
            mock_persist_aws_inspection_cluster_results
    ):
        """Assert empty results does not work."""
        mock_read_messages_from_queue.return_value = []
        tasks.persist_inspection_cluster_results_task()
        mock_read_messages_from_queue.assert_called_once_with(
            settings.HOUNDIGRADE_RESULTS_QUEUE_NAME,
            tasks.HOUNDIGRADE_MESSAGE_READ_LEN
        )
        mock_persist_aws_inspection_cluster_results.assert_not_called()

    def test_persist_aws_inspection_cluster_results_mark_rhel(self):
        """Assert that rhel_images are tagged rhel."""
        ami_id = util_helper.generate_dummy_image_id()
        user1 = util_helper.generate_test_user()
        account1 = helper.generate_aws_account(user=user1)
        machine_image1 = \
            helper.generate_aws_image(account=account1,
                                      is_encrypted=False,
                                      is_windows=False,
                                      ec2_ami_id=ami_id)
        inspection_results = {
            'cloud': 'aws',
            'results': {
                ami_id: {
                    'drive': {
                        'partition': {
                            'rhel_found': True,
                            'evidence': [
                                {
                                    'release_file': '/redhat-release',
                                    'release_file_contents': 'RHEL\n',
                                    'rhel_found': True,
                                }
                            ]
                        }
                    }
                }
            }
        }

        tasks.persist_aws_inspection_cluster_results(inspection_results)
        self.assertEqual(
            machine_image1.tags.filter(description='rhel').first(),
            ImageTag.objects.filter(description='rhel').first())
        self.assertEqual(
            json.loads(AwsMachineImage.objects.filter(
                ec2_ami_id=ami_id).first().inspection_json),
            inspection_results['results'][ami_id])

    def test_persist_aws_inspection_cluster_results(self):
        """Assert that non rhel_images are not tagged rhel."""
        ami_id = util_helper.generate_dummy_image_id()
        user1 = util_helper.generate_test_user()
        account1 = helper.generate_aws_account(user=user1)
        machine_image1 = \
            helper.generate_aws_image(account=account1,
                                      is_encrypted=False,
                                      is_windows=False,
                                      ec2_ami_id=ami_id)

        inspection_results = {
            'cloud': 'aws',
            'results': {
                ami_id: {
                    'drive': {
                        'partition': {
                            'rhel_found': False,
                            'evidence': [
                                {
                                    'release_file': '/centos-release',
                                    'release_file_contents': 'CentOS\n',
                                    'rhel_found': False
                                }
                            ]
                        }
                    }
                }
            }
        }

        tasks.persist_aws_inspection_cluster_results(inspection_results)
        self.assertEqual(machine_image1.tags.first(), None)
        self.assertEqual(
            json.loads(AwsMachineImage.objects.filter(
                ec2_ami_id=ami_id).first().inspection_json),
            inspection_results['results'][ami_id])

    @patch('account.tasks.persist_aws_inspection_cluster_results')
    @patch('account.tasks.read_messages_from_queue')
    def test_persist_inspect_results_unknown_cloud(
            self,
            mock_read_messages_from_queue,
            mock_persist_aws_inspection_cluster_results
    ):
        """Assert no work for unknown cloud."""
        mock_read_messages_from_queue.return_value = [{'cloud': 'unknown'}]
        tasks.persist_inspection_cluster_results_task()
        mock_read_messages_from_queue.assert_called_once_with(
            settings.HOUNDIGRADE_RESULTS_QUEUE_NAME,
            tasks.HOUNDIGRADE_MESSAGE_READ_LEN
        )
        mock_persist_aws_inspection_cluster_results.assert_not_called()

    @patch('account.tasks.persist_aws_inspection_cluster_results')
    @patch('account.tasks.read_messages_from_queue')
    def test_persist_inspect_results_aws_cloud_no_images(
            self,
            mock_read_messages_from_queue,
            mock_persist_aws_inspection_cluster_results
    ):
        """Assert no work for aws cloud without images."""
        message = {'cloud': 'aws'}
        mock_read_messages_from_queue.return_value = [message]
        tasks.persist_inspection_cluster_results_task()
        mock_read_messages_from_queue.assert_called_once_with(
            settings.HOUNDIGRADE_RESULTS_QUEUE_NAME,
            tasks.HOUNDIGRADE_MESSAGE_READ_LEN
        )
        mock_persist_aws_inspection_cluster_results.assert_called_once_with(
            message)

    @patch('account.tasks.persist_aws_inspection_cluster_results')
    @patch('account.tasks.read_messages_from_queue')
    def test_persist_inspect_results_aws_cloud_str_message(
            self,
            mock_read_messages_from_queue,
            mock_persist_aws_inspection_cluster_results
    ):
        """Test case where message is str not python dict."""
        message = json.dumps({'cloud': 'aws'})
        mock_read_messages_from_queue.return_value = [message]
        tasks.persist_inspection_cluster_results_task()
        mock_read_messages_from_queue.assert_called_once_with(
            settings.HOUNDIGRADE_RESULTS_QUEUE_NAME,
            tasks.HOUNDIGRADE_MESSAGE_READ_LEN
        )
        mock_persist_aws_inspection_cluster_results.assert_called_once_with(
            json.loads(message))

    @patch('account.tasks.read_messages_from_queue')
    def test_persist_inspect_results_aws_cloud_image_not_found(
            self,
            mock_read_messages_from_queue
    ):
        """Assert no work for aws cloud with unknown images."""
        message = {'cloud': 'aws', 'results': {'fake_image': {}}}

        mock_read_messages_from_queue.return_value = [message]
        tasks.persist_inspection_cluster_results_task()
        mock_read_messages_from_queue.assert_called_once_with(
            settings.HOUNDIGRADE_RESULTS_QUEUE_NAME,
            tasks.HOUNDIGRADE_MESSAGE_READ_LEN
        )
