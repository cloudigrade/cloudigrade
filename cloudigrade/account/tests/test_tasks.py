"""Collection of tests for celery tasks."""
import random
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from celery.exceptions import Retry
from django.conf import settings
from django.test import TestCase

from account import tasks
from account.models import AwsAccount, AwsMachineImage
from account.tasks import (copy_ami_snapshot,
                           create_volume,
                           enqueue_ready_volume)
from util.exceptions import (AwsSnapshotCopyLimitError,
                             AwsSnapshotEncryptedError,
                             AwsSnapshotNotOwnedError,
                             AwsVolumeError,
                             AwsVolumeNotReadyError,
                             SnapshotNotReadyException)
from util.tests import helper as util_helper


class AccountCeleryTaskTest(TestCase):
    """Account app Celery task test cases."""

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
        mock_aws.add_snapshot_ownership.assert_called_with(
            mock_session,
            mock_snapshot,
            mock_region
        )
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
            account_arn=mock_arn
        )
        account.save()
        ami = AwsMachineImage.objects.create(
            account=account,
            is_windows=False,
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

        mock_queue.assert_called_with('ready_volumes', messages)

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
        mock_aws.is_scaled_down.return_value = True
        mock_read_messages_from_queue.return_value = messages

        tasks.scale_up_inspection_cluster()

        mock_aws.is_scaled_down.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
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
        mock_aws.is_scaled_down.return_value = False

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
        mock_aws.is_scaled_down.return_value = True
        mock_read_messages_from_queue.return_value = []

        tasks.scale_up_inspection_cluster()

        mock_aws.is_scaled_down.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_aws.scale_up.assert_not_called()
        mock_read_messages_from_queue.assert_called_once()
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
        mock_aws.is_scaled_down.return_value = True
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
            'ready_volumes',
            messages
        )
        mock_run_inspection_cluster.delay.assert_not_called()
