"""Collection of tests for celery tasks."""
import datetime
import json
import random
import uuid
from unittest.mock import MagicMock, Mock, call, patch

from botocore.exceptions import ClientError
from celery.exceptions import Retry
from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from api import tasks
from api.models import (AwsInstance,
                        AwsMachineImage,
                        AwsMachineImageCopy,
                        Instance,
                        InstanceEvent,
                        MachineImage)
from api.tasks import (_build_container_definition,
                       aws,
                       copy_ami_snapshot,
                       copy_ami_to_customer_account,
                       create_volume,
                       delete_snapshot,
                       enqueue_ready_volume,
                       remove_snapshot_ownership,
                       scale_down_cluster)
from api.tests import helper as account_helper
from util.exceptions import (AwsECSInstanceNotReady, AwsSnapshotCopyLimitError,
                             AwsSnapshotError,
                             AwsSnapshotNotOwnedError, AwsTooManyECSInstances,
                             AwsVolumeError, AwsVolumeNotReadyError,
                             InvalidHoundigradeJsonFormat,
                             SnapshotNotReadyException)
from util.tests import helper as util_helper
from util.tests.helper import generate_dummy_image_id
from . import helper


class AccountCeleryTaskTest(TestCase):
    """Account app Celery task test cases."""

    def setUp(self):
        """Set up expected ready_volumes queue name."""
        self.ready_volumes_queue_name = '{0}ready_volumes'.format(
            settings.AWS_NAME_PREFIX
        )

    @patch('api.tasks.aws')
    @patch('api.util.aws')
    def test_initial_aws_describe_instances(self, mock_util_aws, mock_aws):
        """
        Test happy-path behaviors of initial_aws_describe_instances.

        This test simulates a situation in which three running instances are
        found. One instance has the Windows platform, another instance has its
        image tagged for OpenShift, and a third instance has neither of those.

        The end result is that the three running instances should be saved,
        three power-on events should be saved (one for each instance), three
        images should be saved, and two new tasks should be spawned for
        inspecting the two not-windows images.
        """
        account = account_helper.generate_aws_account()

        # Set up mocked data in AWS API responses.
        region = util_helper.get_random_region()
        described_ami_unknown = util_helper.generate_dummy_describe_image()
        described_ami_openshift = util_helper.generate_dummy_describe_image(
            openshift=True,
        )
        described_ami_windows = util_helper.generate_dummy_describe_image()

        ami_id_unknown = described_ami_unknown['ImageId']
        ami_id_openshift = described_ami_openshift['ImageId']
        ami_id_windows = described_ami_windows['ImageId']
        ami_id_unavailable = generate_dummy_image_id()
        ami_id_gone = generate_dummy_image_id()

        all_instances = [
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_unknown,
                state=aws.InstanceState.running
            ),
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_openshift,
                state=aws.InstanceState.running
            ),
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_windows,
                state=aws.InstanceState.running,
                platform=AwsMachineImage.WINDOWS,
            ),
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_unavailable,
                state=aws.InstanceState.running
            ),
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_gone,
                state=aws.InstanceState.terminated
            ),

        ]
        described_instances = {
            region: all_instances,
        }

        mock_aws.describe_instances_everywhere.return_value = (
            described_instances
        )
        mock_util_aws.describe_images.return_value = [
            described_ami_unknown,
            described_ami_openshift,
            described_ami_windows,
        ]
        mock_util_aws.is_windows.side_effect = aws.is_windows
        mock_util_aws.OPENSHIFT_TAG = aws.OPENSHIFT_TAG
        mock_util_aws.InstanceState.is_running = aws.InstanceState.is_running

        start_inspection_calls = [
            call(account.content_object.account_arn,
                 described_ami_unknown['ImageId'],
                 region),
            call(account.content_object.account_arn,
                 described_ami_openshift['ImageId'],
                 region),
        ]

        with patch.object(tasks, 'start_image_inspection') as mock_start:
            tasks.initial_aws_describe_instances(account.id)
            mock_start.assert_has_calls(start_inspection_calls)

        # Verify that we created all five instances.
        instances_count = Instance.objects.filter(
            cloud_account=account
        ).count()
        self.assertEqual(instances_count, 5)

        # Verify that the running instances exist with power-on events.
        for described_instance in all_instances[:4]:
            instance_id = described_instance['InstanceId']
            aws_instance = AwsInstance.objects.get(
                ec2_instance_id=instance_id
            )
            self.assertIsInstance(aws_instance, AwsInstance)
            self.assertEqual(region, aws_instance.region)
            event = InstanceEvent.objects.get(
                instance=aws_instance.instance.get()
            )
            self.assertIsInstance(event, InstanceEvent)
            self.assertEqual(InstanceEvent.TYPE.power_on, event.event_type)

        # Verify that the not-running instances exist with no events.
        for described_instance in all_instances[4:]:
            instance_id = described_instance['InstanceId']
            aws_instance = AwsInstance.objects.get(ec2_instance_id=instance_id)
            self.assertIsInstance(aws_instance, AwsInstance)
            self.assertEqual(region, aws_instance.region)
            self.assertFalse(
                InstanceEvent.objects.filter(
                    instance=aws_instance.instance.get()
                ).exists()
            )

        # Verify that we saved images for all instances, even if not running.
        images_count = AwsMachineImage.objects.count()
        self.assertEqual(images_count, 5)

        aws_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id_unknown)
        image = aws_image.machine_image.get()
        self.assertFalse(image.rhel_detected)
        self.assertFalse(image.openshift_detected)
        self.assertEqual(image.name, described_ami_unknown['Name'])

        aws_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id_openshift)
        image = aws_image.machine_image.get()
        self.assertFalse(image.rhel_detected)
        self.assertTrue(image.openshift_detected)
        self.assertEqual(image.name, described_ami_openshift['Name'])

        aws_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id_windows)
        image = aws_image.machine_image.get()
        self.assertFalse(image.rhel_detected)
        self.assertFalse(image.openshift_detected)
        self.assertEqual(image.name, described_ami_windows['Name'])
        self.assertEqual(aws_image.platform, AwsMachineImage.WINDOWS)

        aws_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id_unavailable)
        image = aws_image.machine_image.get()
        self.assertFalse(image.rhel_detected)
        self.assertFalse(image.openshift_detected)
        self.assertEqual(image.status, MachineImage.UNAVAILABLE)

    @patch('api.tasks.aws')
    def test_initial_aws_describe_instances_missing_account(self, mock_aws):
        """Test early return when account does not exist."""
        account_id = -1  # negative number account ID should never exist.
        tasks.initial_aws_describe_instances(account_id)
        mock_aws.get_session.assert_not_called()

    @patch('api.tasks.aws')
    def test_copy_ami_snapshot_success(self, mock_aws):
        """Assert that the snapshot copy task succeeds."""
        mock_session = mock_aws.boto3.Session.return_value
        mock_account_id = mock_aws.get_session_account_id.return_value

        mock_arn = util_helper.generate_dummy_arn()
        mock_region = util_helper.get_random_region()
        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        account_helper.generate_aws_image(ec2_ami_id=mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]['Ebs']['SnapshotId']
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id,
            owner_id=mock_account_id
        )
        mock_new_snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot
        mock_aws.copy_snapshot.return_value = mock_new_snapshot_id

        with patch.object(tasks, 'create_volume') as mock_create_volume:
            with patch.object(tasks, 'remove_snapshot_ownership') as \
                    mock_remove_snapshot_ownership:
                copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
                mock_create_volume.delay.assert_called_with(
                    mock_image_id, mock_new_snapshot_id)
                mock_remove_snapshot_ownership.delay.assert_called_with(
                    mock_arn,
                    mock_snapshot_id,
                    mock_region,
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

    @patch('api.tasks.aws')
    def test_copy_ami_snapshot_success_with_reference(self, mock_aws):
        """Assert the snapshot copy task succeeds using a reference AMI ID."""
        mock_session = mock_aws.boto3.Session.return_value
        mock_account_id = mock_aws.get_session_account_id.return_value

        account = account_helper.generate_aws_account()
        arn = account.content_object.account_arn

        region = util_helper.get_random_region()
        new_image_id = util_helper.generate_dummy_image_id()
        # unlike non-reference calls to copy_ami_snapshot, we do NOT want to
        # call "account_helper.generate_aws_image(ec2_ami_id=new_image_id)"
        # here because cloudigrade has only seen the reference, not the new.
        mock_image = util_helper.generate_mock_image(new_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]['Ebs']['SnapshotId']
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id,
            owner_id=mock_account_id
        )
        mock_new_snapshot_id = util_helper.generate_dummy_snapshot_id()

        # This is the original ID of a private/shared image.
        # It would have been saved to our DB upon initial discovery.
        reference_image = account_helper.generate_aws_image()
        reference_image_id = reference_image.content_object.ec2_ami_id

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot
        mock_aws.copy_snapshot.return_value = mock_new_snapshot_id

        with patch.object(tasks, 'create_volume') as mock_create_volume, \
                patch.object(tasks, 'remove_snapshot_ownership') as \
                mock_remove_snapshot_ownership:
            tasks.copy_ami_snapshot(
                arn,
                new_image_id,
                region,
                reference_image_id,
            )
            # arn, customer_snapshot_id, snapshot_region, snapshot_copy_id
            mock_remove_snapshot_ownership.delay.assert_called_with(
                arn,
                mock_snapshot_id,
                region,
                mock_new_snapshot_id,
            )
            mock_create_volume.delay.assert_called_with(
                reference_image_id,
                mock_new_snapshot_id,
            )

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_session,
            new_image_id,
            region
        )
        mock_aws.get_ami_snapshot_id.assert_called_with(mock_image)
        mock_aws.add_snapshot_ownership.assert_called_with(mock_snapshot)
        mock_aws.copy_snapshot.assert_called_with(
            mock_snapshot_id,
            region
        )

        # Verify that the copy object was stored correctly to reference later.
        copied_image = AwsMachineImageCopy.objects.get(ec2_ami_id=new_image_id)
        self.assertIsNotNone(copied_image)
        self.assertEqual(copied_image.reference_awsmachineimage.ec2_ami_id,
                         reference_image_id)

    @patch('api.tasks.aws')
    def test_copy_ami_snapshot_encrypted(self, mock_aws):
        """Assert that the task marks the image as encrypted in the DB."""
        mock_account_id = util_helper.generate_dummy_aws_account_id()
        mock_region = util_helper.get_random_region()
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

        ami = account_helper.generate_aws_image(ec2_ami_id=mock_image_id)

        with patch.object(tasks, 'create_volume') as mock_create_volume:
            copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            ami.refresh_from_db()
            self.assertTrue(ami.is_encrypted)
            self.assertEqual(ami.status, ami.ERROR)
            mock_create_volume.delay.assert_not_called()

    @patch('api.tasks.aws')
    def test_copy_ami_snapshot_retry_on_copy_limit(self, mock_aws):
        """Assert that the copy task is retried."""
        mock_session = mock_aws.boto3.Session.return_value
        mock_account_id = mock_aws.get_session_account_id.return_value

        mock_arn = util_helper.generate_dummy_arn()
        mock_region = util_helper.get_random_region()
        mock_image_id = util_helper.generate_dummy_image_id()
        account_helper.generate_aws_image(ec2_ami_id=mock_image_id)
        mock_image = util_helper.generate_mock_image(mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]['Ebs']['SnapshotId']
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id,
            owner_id=mock_account_id
        )

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

    @patch('api.tasks.aws')
    def test_copy_snapshot_missing_image(self, mock_aws):
        """Assert early return if the AwsMachineImage doesn't exist."""
        arn = util_helper.generate_dummy_arn()
        ec2_ami_id = util_helper.generate_dummy_image_id()
        region = util_helper.get_random_region()
        copy_ami_snapshot(arn, ec2_ami_id, region)
        mock_aws.get_session.assert_not_called()

    @patch('api.tasks.aws')
    def test_copy_ami_snapshot_retry_on_ownership_not_verified(self, mock_aws):
        """Assert that the snapshot copy task fails."""
        mock_session = mock_aws.boto3.Session.return_value
        mock_account_id = mock_aws.get_session_account_id.return_value

        mock_arn = util_helper.generate_dummy_arn()
        mock_region = util_helper.get_random_region()
        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        account_helper.generate_aws_image(ec2_ami_id=mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]['Ebs']['SnapshotId']
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id,
            owner_id=mock_account_id
        )

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

    @patch('api.tasks.boto3')
    @patch('api.tasks.aws')
    def test_remove_snapshot_ownership_success(self,
                                               mock_aws,
                                               mock_boto3):
        """Assert that the remove snapshot ownership task succeeds."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_customer_snapshot_id = util_helper.generate_dummy_snapshot_id()
        mock_customer_snapshot = util_helper.generate_mock_snapshot(
            mock_customer_snapshot_id)
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot_copy = util_helper.generate_mock_snapshot(
            mock_snapshot_copy_id)
        zone = settings.HOUNDIGRADE_AWS_AVAILABILITY_ZONE
        region = zone[:-1]

        resource = mock_boto3.resource.return_value
        resource.Snapshot.return_value = mock_snapshot_copy

        mock_aws.check_snapshot_state.return_value = None
        mock_aws.get_snapshot.return_value = mock_customer_snapshot

        mock_aws.get_region_from_availability_zone.return_value = region

        remove_snapshot_ownership(mock_arn,
                                  mock_customer_snapshot_id,
                                  region,
                                  mock_snapshot_copy_id)

        mock_aws.remove_snapshot_ownership.assert_called_with(
            mock_customer_snapshot)

    @patch('api.tasks.boto3')
    @patch('api.tasks.aws')
    def test_remove_snapshot_ownership_no_copy_snapshot(self,
                                                        mock_aws,
                                                        mock_boto3):
        """Assert remove snapshot ownership task succeeds with missing copy."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_customer_snapshot_id = util_helper.generate_dummy_snapshot_id()
        mock_customer_snapshot = util_helper.generate_mock_snapshot(
            mock_customer_snapshot_id)
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot_copy = util_helper.generate_mock_snapshot(
            mock_snapshot_copy_id)
        zone = settings.HOUNDIGRADE_AWS_AVAILABILITY_ZONE
        region = zone[:-1]

        client_error = ClientError(
            error_response={'Error': {'Code': 'InvalidSnapshot.NotFound'}},
            operation_name=Mock(),
        )

        resource = mock_boto3.resource.return_value
        resource.Snapshot.return_value = mock_snapshot_copy
        resource.Snapshot.side_effect = client_error

        mock_aws.check_snapshot_state.return_value = None
        mock_aws.get_snapshot.return_value = mock_customer_snapshot

        mock_aws.get_region_from_availability_zone.return_value = region

        remove_snapshot_ownership(mock_arn,
                                  mock_customer_snapshot_id,
                                  region,
                                  mock_snapshot_copy_id)

        mock_aws.remove_snapshot_ownership.assert_called_with(
            mock_customer_snapshot)

    @patch('api.tasks.boto3')
    @patch('api.tasks.aws')
    def test_remove_snapshot_ownership_unexpected_error(self,
                                                        mock_aws,
                                                        mock_boto3):
        """Assert remove snapshot ownership fails due to unexpected error."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_customer_snapshot_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        zone = settings.HOUNDIGRADE_AWS_AVAILABILITY_ZONE
        region = zone[:-1]

        client_error = ClientError(
            error_response={'Error': {'Code': 'InvalidSnapshot.Unknown'}},
            operation_name=Mock(),
        )

        resource = mock_boto3.resource.return_value
        resource.Snapshot.side_effect = client_error

        with self.assertRaises(RuntimeError):
            remove_snapshot_ownership(mock_arn,
                                      mock_customer_snapshot_id,
                                      region,
                                      mock_snapshot_copy_id)

        mock_aws.remove_snapshot_ownership.assert_not_called()

    @patch('api.tasks.boto3')
    @patch('api.tasks.aws')
    def test_delete_snapshot_success(self, mock_aws, mock_boto3):
        """Assert that the delete snapshot succeeds."""
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot_copy = util_helper.generate_mock_snapshot(
            mock_snapshot_copy_id)

        resource = mock_boto3.resource.return_value
        resource.Snapshot.return_value = mock_snapshot_copy

        volume_id = util_helper.generate_dummy_volume_id()
        mock_volume = util_helper.generate_mock_volume(
            volume_id=volume_id,
            state='available'
        )
        volume_region = mock_volume.zone[:-1]

        mock_aws.get_volume.return_value = mock_volume
        mock_aws.check_volume_state.return_value = None

        delete_snapshot(mock_snapshot_copy_id,
                        volume_id,
                        volume_region)

    @patch('api.tasks.aws')
    def test_copy_ami_snapshot_private_shared(self, mock_aws):
        """Assert that the task copies the image when it is private/shared."""
        mock_account_id = util_helper.generate_dummy_aws_account_id()
        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session_account_id.return_value = mock_account_id

        # the account id to use as the private shared image owner
        other_account_id = util_helper.generate_dummy_aws_account_id()

        mock_region = util_helper.get_random_region()
        mock_arn = util_helper.generate_dummy_arn(mock_account_id, mock_region)

        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        mock_snapshot_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id,
            encrypted=False,
            owner_id=other_account_id
        )

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot

        account_helper.generate_aws_image(ec2_ami_id=mock_image_id)

        with patch.object(tasks, 'create_volume') as mock_create_volume, \
                patch.object(tasks, 'copy_ami_to_customer_account') as \
                mock_copy_ami_to_customer_account:
            copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            mock_create_volume.delay.assert_not_called()
            mock_copy_ami_to_customer_account.delay.assert_called_with(
                mock_arn, mock_image_id, mock_region
            )

    @patch('api.tasks.aws')
    def test_copy_ami_snapshot_marketplace(self, mock_aws):
        """Assert that a suspected marketplace image is checked."""
        mock_account_id = util_helper.generate_dummy_aws_account_id()
        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session_account_id.return_value = mock_account_id

        mock_region = util_helper.get_random_region()
        mock_arn = util_helper.generate_dummy_arn(mock_account_id, mock_region)

        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        mock_snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.side_effect = ClientError(
            error_response={'Error': {'Code': 'InvalidSnapshot.NotFound'}},
            operation_name=Mock(),
        )

        account_helper.generate_aws_image(ec2_ami_id=mock_image_id)

        with patch.object(tasks, 'create_volume') as mock_create_volume, \
                patch.object(tasks, 'copy_ami_to_customer_account') as \
                mock_copy_ami_to_customer_account:
            copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            mock_create_volume.delay.assert_not_called()
            mock_copy_ami_to_customer_account.delay.assert_called_with(
                mock_arn, mock_image_id, mock_region)

    @patch('api.tasks.aws')
    def test_copy_ami_snapshot_not_marketplace(self, mock_aws):
        """Assert that an exception is raised when there is an error."""
        mock_account_id = util_helper.generate_dummy_aws_account_id()
        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session_account_id.return_value = mock_account_id

        mock_region = util_helper.get_random_region()
        mock_arn = util_helper.generate_dummy_arn(mock_account_id, mock_region)

        mock_image_id = util_helper.generate_dummy_image_id()
        account_helper.generate_aws_image(ec2_ami_id=mock_image_id)
        mock_image = util_helper.generate_mock_image(mock_image_id)
        mock_snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.side_effect = ClientError(
            error_response={'Error': {
                'Code': 'ItIsAMystery',
                'Message': 'Mystery Error',
            }},
            operation_name=Mock(),
        )

        with self.assertRaises(RuntimeError) as e:
            copy_ami_snapshot(mock_arn, mock_image_id, mock_region)

        self.assertIn('ClientError', e.exception.args[0])
        self.assertIn('ItIsAMystery', e.exception.args[0])
        self.assertIn('Mystery Error', e.exception.args[0])

    @patch('api.tasks.aws')
    def test_copy_ami_snapshot_save_error_when_image_load_fails(
        self, mock_aws
    ):
        """Assert that we save error status if image load fails."""
        arn = util_helper.generate_dummy_arn()
        ami_id = util_helper.generate_dummy_image_id()
        snapshot_region = util_helper.get_random_region()
        image = account_helper.generate_aws_image(ec2_ami_id=ami_id)

        mock_aws.get_ami.return_value = None

        with patch.object(
            tasks, 'create_volume'
        ) as mock_create_volume, patch.object(
            tasks, 'copy_ami_to_customer_account'
        ) as mock_copy_ami_to_customer_account:
            copy_ami_snapshot(arn, ami_id, snapshot_region)
            mock_create_volume.delay.assert_not_called()
            mock_copy_ami_to_customer_account.delay.assert_not_called()

        image.refresh_from_db()
        self.assertEquals(image.status, image.ERROR)

    @patch('api.tasks.aws')
    def test_copy_ami_snapshot_save_error_when_image_snapshot_id_get_fails(
        self, mock_aws
    ):
        """Assert that we save error status if snapshot id is not available."""
        arn = util_helper.generate_dummy_arn()
        ami_id = util_helper.generate_dummy_image_id()
        snapshot_region = util_helper.get_random_region()
        image = account_helper.generate_aws_image(ec2_ami_id=ami_id)

        mock_aws.get_ami.return_value = image
        mock_aws.get_ami_snapshot_id.return_value = None

        with patch.object(
            tasks, 'create_volume'
        ) as mock_create_volume, patch.object(
            tasks, 'copy_ami_to_customer_account'
        ) as mock_copy_ami_to_customer_account:
            copy_ami_snapshot(arn, ami_id, snapshot_region)
            mock_create_volume.delay.assert_not_called()
            mock_copy_ami_to_customer_account.delay.assert_not_called()

        image.refresh_from_db()
        self.assertEquals(image.status, image.ERROR)

    @patch('api.tasks.aws')
    def test_copy_ami_to_customer_account_success(self, mock_aws):
        """Assert that the task copies image using appropriate boto calls."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()

        helper.generate_aws_image(ec2_ami_id=reference_ami_id)

        new_ami_id = mock_aws.copy_ami.return_value

        with patch.object(tasks, 'copy_ami_snapshot') as \
                mock_copy_ami_snapshot:
            copy_ami_to_customer_account(arn, reference_ami_id, source_region)
            mock_copy_ami_snapshot.delay.assert_called_with(
                arn, new_ami_id, source_region, reference_ami_id
            )

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )
        reference_ami = mock_aws.get_ami.return_value
        mock_aws.copy_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami.id, source_region
        )

    @patch('api.tasks.aws')
    def test_copy_ami_to_customer_account_marketplace(
            self, mock_aws):
        """Assert that the task marks marketplace image as inspected."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()

        image = account_helper.generate_aws_image(
            ec2_ami_id=reference_ami_id,
            status=MachineImage.INSPECTING
        )

        mock_reference_ami = Mock()
        mock_reference_ami.public = True
        mock_aws.get_ami.return_value = mock_reference_ami

        mock_aws.copy_ami.side_effect = ClientError(
            error_response={'Error': {
                'Code': 'InvalidRequest',
                'Message': 'Images with EC2 BillingProduct codes cannot be '
                           'copied to another AWS account',
            }},
            operation_name=Mock(),
        )

        copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )

        image.refresh_from_db()
        aws_image = image.content_object
        aws_image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.INSPECTED)
        self.assertTrue(aws_image.aws_marketplace_image)

    @patch('api.tasks.aws')
    def test_copy_ami_to_customer_account_marketplace_with_dot_error(
            self, mock_aws):
        """Assert that the task marks marketplace image as inspected."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()
        image = account_helper.generate_aws_image(
            ec2_ami_id=reference_ami_id,
            status=MachineImage.INSPECTING
        )

        mock_aws.copy_ami.side_effect = ClientError(
            error_response={'Error': {
                'Code': 'InvalidRequest',
                'Message': 'Images with EC2 BillingProduct codes cannot be '
                           'copied to another AWS account.',
            }},
            operation_name=Mock(),
        )

        copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )
        image.refresh_from_db()
        aws_image = image.content_object
        aws_image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.INSPECTED)
        self.assertTrue(aws_image.aws_marketplace_image)

    @patch('api.tasks.aws')
    def test_copy_ami_to_customer_account_missing_image(self, mock_aws):
        """Assert early return if the AwsMachineImage doesn't exist."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        region = util_helper.get_random_region()
        copy_ami_to_customer_account(arn, reference_ami_id, region)
        mock_aws.get_session.assert_not_called()

    @patch('api.tasks.aws')
    def test_copy_ami_to_customer_account_community(
            self, mock_aws):
        """Assert that the task marks community image as inspected."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()
        image = account_helper.generate_aws_image(
            ec2_ami_id=reference_ami_id,
            status=MachineImage.INSPECTING
        )
        mock_aws.copy_ami.side_effect = ClientError(
            error_response={'Error': {
                'Code': 'InvalidRequest',
                'Message': 'Images from AWS Marketplace cannot be copied to '
                           'another AWS account',
            }},
            operation_name=Mock(),
        )
        copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )

        image.refresh_from_db()
        aws_image = image.content_object
        aws_image.refresh_from_db()

        self.assertEqual(image.status, image.INSPECTED)
        self.assertTrue(aws_image.aws_marketplace_image)

    @patch('api.tasks.aws')
    def test_copy_ami_to_customer_account_private_no_copy(
            self, mock_aws):
        """Assert that the task marks private (no copy) image as in error."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()

        image = account_helper.generate_aws_image(
            ec2_ami_id=reference_ami_id,
            status=MachineImage.INSPECTING
        )

        mock_reference_ami = Mock()
        mock_reference_ami.public = False
        mock_aws.get_ami.return_value = mock_reference_ami

        mock_aws.copy_ami.side_effect = ClientError(
            error_response={'Error': {
                'Code': 'InvalidRequest',
                'Message': 'You do not have permission to access the storage '
                           'of this ami',
            }},
            operation_name=Mock(),
        )

        copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        image.refresh_from_db()

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )
        self.assertEqual(image.status, MachineImage.ERROR)

    @patch('api.tasks.aws')
    def test_copy_ami_to_customer_account_private_no_copy_dot_error(
            self, mock_aws):
        """Assert that the task marks private (no copy) image as in error."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()
        image = account_helper.generate_aws_image(
            ec2_ami_id=reference_ami_id,
            status=MachineImage.INSPECTING
        )
        mock_reference_ami = Mock()
        mock_reference_ami.public = False
        mock_aws.get_ami.return_value = mock_reference_ami

        mock_aws.copy_ami.side_effect = ClientError(
            error_response={'Error': {
                'Code': 'InvalidRequest',
                'Message': 'You do not have permission to access the storage '
                           'of this ami.',
            }},
            operation_name=Mock(),
        )

        copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )
        image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.ERROR)

    @patch('api.tasks.aws')
    def test_copy_ami_to_customer_account_not_marketplace(self, mock_aws):
        """Assert that the task fails when non-marketplace error occurs."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()

        helper.generate_aws_image(ec2_ami_id=reference_ami_id)

        mock_aws.copy_ami.side_effect = ClientError(
            error_response={'Error': {
                'Code': 'ItIsAMystery',
                'Message': 'Mystery Error',
            }},
            operation_name=Mock(),
        )

        with self.assertRaises(RuntimeError) as e:
            copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        self.assertIn('ClientError', e.exception.args[0])
        self.assertIn('ItIsAMystery', e.exception.args[0])
        self.assertIn('Mystery Error', e.exception.args[0])

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )

    @patch('api.tasks.aws')
    def test_copy_ami_to_customer_account_save_error_when_image_load_fails(
        self, mock_aws
    ):
        """Assert that we save error status if image load fails."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        snapshot_region = util_helper.get_random_region()
        image = account_helper.generate_aws_image(ec2_ami_id=reference_ami_id)

        mock_aws.get_ami.return_value = None
        with patch.object(tasks, 'copy_ami_snapshot') as mock_copy:
            copy_ami_to_customer_account(
                arn, reference_ami_id, snapshot_region
            )
            mock_copy.delay.assert_not_called()
        mock_aws.copy_ami.assert_not_called()

        image.refresh_from_db()
        self.assertEquals(image.status, image.ERROR)

    @patch('api.tasks.aws')
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
            with patch.object(tasks, 'delete_snapshot') as \
                    mock_delete_snapshot:
                create_volume(ami_id, snapshot_id)
                mock_enqueue.delay.assert_called_with(
                    ami_id,
                    mock_volume.id,
                    region
                )
                mock_delete_snapshot.delay.assert_called_with(
                    snapshot_id,
                    mock_volume.id,
                    region
                )

        mock_aws.create_volume.assert_called_with(snapshot_id, zone)

    @patch('api.tasks.aws')
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

    @patch('api.tasks.aws')
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

    @patch('api.tasks.add_messages_to_queue')
    @patch('api.tasks.aws')
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

    @patch('api.tasks.aws')
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

    @patch('api.tasks.aws')
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

    @patch('api.tasks.add_messages_to_queue')
    @patch('api.tasks.run_inspection_cluster')
    @patch('api.tasks.read_messages_from_queue')
    @patch('api.tasks.aws')
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

    @patch('api.tasks.add_messages_to_queue')
    @patch('api.tasks.run_inspection_cluster')
    @patch('api.tasks.read_messages_from_queue')
    @patch('api.tasks.aws')
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

    @patch('api.tasks.add_messages_to_queue')
    @patch('api.tasks.run_inspection_cluster')
    @patch('api.tasks.read_messages_from_queue')
    @patch('api.tasks.aws')
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

    @patch('api.tasks.add_messages_to_queue')
    @patch('api.tasks.run_inspection_cluster')
    @patch('api.tasks.read_messages_from_queue')
    @patch('api.tasks.aws')
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

    @patch('api.tasks.boto3')
    @patch('api.tasks.aws')
    def test_run_inspection_cluster_success(
            self, mock_aws, mock_boto3):
        """Asserts successful starting of the houndigrade task."""
        mock_ami_id = util_helper.generate_dummy_image_id()

        image = account_helper.generate_aws_image(
            ec2_ami_id=mock_ami_id,
            status=MachineImage.PENDING
        )

        mock_list_container_instances = {
            'containerInstanceArns': [util_helper.generate_dummy_instance_id()]
        }
        mock_ec2 = Mock()
        mock_ecs = MagicMock()

        mock_ecs.list_container_instances.return_value = \
            mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs
        mock_boto3.resource.return_value = mock_ec2

        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session.return_value = mock_session

        messages = [{
            'ami_id': mock_ami_id,
            'volume_id': util_helper.generate_dummy_volume_id()}]
        tasks.run_inspection_cluster(messages)

        image.refresh_from_db()

        self.assertEqual(image.status,
                         MachineImage.INSPECTING)

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

    @patch('api.tasks.settings')
    def test_build_container_definition_with_sentry(self, mock_s):
        """Assert successful build of definition with sentry params."""
        enable_sentry = True
        sentry_dsn = 'dsn'
        sentry_release = '1.3.3.7'
        sentry_environment = 'test'

        expected_result = [
            {'name': 'HOUNDIGRADE_SENTRY_DSN', 'value': sentry_dsn},
            {'name': 'HOUNDIGRADE_SENTRY_RELEASE', 'value': sentry_release},
            {'name': 'HOUNDIGRADE_SENTRY_ENVIRONMENT',
             'value': sentry_environment}]

        mock_s.HOUNDIGRADE_ENABLE_SENTRY = enable_sentry
        mock_s.HOUNDIGRADE_SENTRY_DSN = sentry_dsn
        mock_s.HOUNDIGRADE_SENTRY_RELEASE = sentry_release
        mock_s.HOUNDIGRADE_SENTRY_ENVIRONMENT = sentry_environment

        task_command = ['-c', 'aws', '-t', 'ami-test', '/dev/sdba']

        result = _build_container_definition(task_command)
        for entry in expected_result:
            self.assertIn(entry, result['environment'])

    def test_build_container_definition_without_sentry(self):
        """Assert successful build of definition with no sentry params."""
        task_command = ['-c', 'aws', '-t', 'ami-test', '/dev/sdba']

        result = _build_container_definition(task_command)

        self.assertEqual(
            result['image'], f'{settings.HOUNDIGRADE_ECS_IMAGE_NAME}:'
                             f'{settings.HOUNDIGRADE_ECS_IMAGE_TAG}')
        self.assertEqual(result['command'], task_command)
        self.assertEqual(result['environment'][0]['value'],
                         settings.AWS_SQS_REGION)
        self.assertEqual(result['environment'][1]['value'],
                         settings.AWS_SQS_ACCESS_KEY_ID)
        self.assertEqual(result['environment'][2]['value'],
                         settings.AWS_SQS_SECRET_ACCESS_KEY)
        self.assertEqual(result['environment'][3]['value'],
                         settings.HOUNDIGRADE_RESULTS_QUEUE_NAME)
        self.assertEqual(result['environment'][4]['value'],
                         settings.HOUNDIGRADE_EXCHANGE_NAME)
        self.assertEqual(result['environment'][5]['value'],
                         settings.CELERY_BROKER_URL)

    @patch('api.models.AwsMachineImage.objects')
    @patch('api.tasks.boto3')
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

    @patch('api.tasks.boto3')
    def test_run_inspection_cluster_with_no_known_images(self, mock_boto3):
        """Assert that inspection is skipped if no known images are given."""
        messages = [{'ami_id': util_helper.generate_dummy_image_id()}]
        tasks.run_inspection_cluster(messages)
        mock_boto3.client.assert_not_called()

    @patch('api.models.AwsMachineImage.objects')
    @patch('api.tasks.boto3')
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

    @patch('api.tasks.boto3')
    @patch('api.tasks.aws')
    def test_run_inspection_cluster_with_marketplace_volume(
            self, mock_aws, mock_boto3):
        """Assert that ami is marked as inspected if marketplace volume."""
        mock_ami_id = util_helper.generate_dummy_image_id()

        image = account_helper.generate_aws_image(
            ec2_ami_id=mock_ami_id,
            status=MachineImage.PENDING
        )

        mock_list_container_instances = {
            'containerInstanceArns': [util_helper.generate_dummy_instance_id()]
        }
        mock_ec2 = Mock()
        mock_ecs = MagicMock()

        mock_volume = mock_ec2.Volume.return_value

        mock_volume.attach_to_instance.side_effect = ClientError(
            error_response={'Error': {
                'Code': 'OptInRequired',
                'Message': 'Marketplace Error',
            }},
            operation_name=Mock(),
        )

        mock_ecs.list_container_instances.return_value = \
            mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs
        mock_boto3.resource.return_value = mock_ec2

        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session.return_value = mock_session

        messages = [{
            'ami_id': mock_ami_id,
            'volume_id': util_helper.generate_dummy_volume_id()}]

        tasks.run_inspection_cluster(messages)
        image.refresh_from_db()

        self.assertEqual(image.status,
                         MachineImage.INSPECTED)

        mock_ecs.list_container_instances.assert_called_once_with(
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME)
        mock_ecs.describe_container_instances.assert_called_once_with(
            containerInstances=[
                mock_list_container_instances['containerInstanceArns'][0]],
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME
        )
        mock_ecs.register_task_definition.assert_not_called()
        mock_ecs.run_task.assert_not_called()

        mock_ec2.Volume.assert_called_once_with(messages[0]['volume_id'])
        mock_ec2.Volume.return_value.attach_to_instance.assert_called_once()

    @patch('api.tasks.boto3')
    @patch('api.tasks.aws')
    def test_run_inspection_cluster_with_unknown_error(
            self, mock_aws, mock_boto3):
        """Assert that non marketplace errors are still raised."""
        mock_ami_id = util_helper.generate_dummy_image_id()

        image = account_helper.generate_aws_image(
            ec2_ami_id=mock_ami_id,
            status=MachineImage.PENDING
        )

        mock_list_container_instances = {
            'containerInstanceArns': [util_helper.generate_dummy_instance_id()]
        }
        mock_ec2 = Mock()
        mock_ecs = MagicMock()

        mock_volume = mock_ec2.Volume.return_value

        mock_volume.attach_to_instance.side_effect = ClientError(
            error_response={'Error': {
                'Code': 'ItIsAMystery',
                'Message': 'Mystery Error',
            }},
            operation_name=Mock(),
        )

        mock_ecs.list_container_instances.return_value = \
            mock_list_container_instances

        mock_boto3.client.return_value = mock_ecs
        mock_boto3.resource.return_value = mock_ec2

        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session.return_value = mock_session

        messages = [{
            'ami_id': mock_ami_id,
            'volume_id': util_helper.generate_dummy_volume_id()}]

        tasks.run_inspection_cluster(messages)
        image.refresh_from_db()

        self.assertEqual(image.status,
                         MachineImage.ERROR)

        mock_ecs.list_container_instances.assert_called_once_with(
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME)
        mock_ecs.describe_container_instances.assert_called_once_with(
            containerInstances=[
                mock_list_container_instances['containerInstanceArns'][0]],
            cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME
        )
        mock_ecs.register_task_definition.assert_not_called()
        mock_ecs.run_task.assert_not_called()

        mock_ec2.Volume.assert_called_once_with(messages[0]['volume_id'])
        mock_ec2.Volume.return_value.attach_to_instance.assert_called_once()

    @patch('api.tasks.aws.yield_messages_from_queue')
    @patch('api.tasks.aws.get_sqs_queue_url')
    @patch('api.tasks.scale_down_cluster')
    @patch('api.tasks.persist_aws_inspection_cluster_results')
    def test_persist_inspect_results_no_messages(
            self, mock_persist, mock_scale_down, _, mock_receive):
        """Assert empty yield results are properly ignored."""
        mock_receive.return_value = []
        tasks.persist_inspection_cluster_results_task()
        mock_persist.assert_not_called()
        mock_scale_down.assert_not_called()

    def test_persist_aws_inspection_cluster_results_mark_rhel(self):
        """Assert that rhel_images are tagged rhel."""
        ami_id = util_helper.generate_dummy_image_id()
        helper.generate_aws_image(is_encrypted=False,
                                  is_windows=False,
                                  ec2_ami_id=ami_id)
        inspection_results = {
            'cloud': 'aws',
            'images': {
                ami_id: {
                    'rhel_found': True,
                    'rhel_release_files_found': True,
                    'drive': {
                        'partition': {
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
        aws_machine_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        machine_image = aws_machine_image.machine_image.get()
        self.assertTrue(machine_image.rhel_detected)
        self.assertEqual(
            json.loads(machine_image.inspection_json),
            inspection_results['images'][ami_id])
        self.assertTrue(machine_image.rhel)
        self.assertFalse(machine_image.openshift)

    def test_persist_aws_inspection_cluster_results(self):
        """Assert that non rhel_images are not tagged rhel."""
        ami_id = util_helper.generate_dummy_image_id()
        helper.generate_aws_image(is_encrypted=False,
                                  is_windows=False,
                                  ec2_ami_id=ami_id)

        inspection_results = {
            'cloud': 'aws',
            'images': {
                ami_id: {
                    'rhel_found': False,
                    'drive': {
                        'partition': {
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
        aws_machine_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        machine_image = aws_machine_image.machine_image.get()
        self.assertFalse(machine_image.rhel_detected)
        self.assertFalse(machine_image.openshift_detected)
        self.assertEqual(
            json.loads(machine_image.inspection_json),
            inspection_results['images'][ami_id])
        self.assertFalse(machine_image.rhel)
        self.assertFalse(machine_image.openshift)

    def test_persist_aws_inspection_cluster_results_our_model_is_gone(self):
        """
        Assert that we handle when the AwsMachineImage model has been deleted.

        This can happen if the customer deletes their cloud account while we
        are running or waiting on the async inspection. Deleting the cloud
        account results in the instances and potentially the images being
        deleted, and when we get the inspection results back for that deleted
        image, we should just quietly drop the results and move on to other
        results that may still need processing.
        """
        deleted_ami_id = util_helper.generate_dummy_image_id()

        ami_id = util_helper.generate_dummy_image_id()
        helper.generate_aws_image(
            is_encrypted=False, is_windows=False, ec2_ami_id=ami_id
        )

        inspection_results = {
            'cloud': 'aws',
            'images': {
                deleted_ami_id: {
                    'rhel_found': True, 'rhel_release_files_found': True
                },
                ami_id: {'rhel_found': True, 'rhel_release_files_found': True},
            },
        }

        tasks.persist_aws_inspection_cluster_results(inspection_results)
        aws_machine_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        machine_image = aws_machine_image.machine_image.get()
        self.assertTrue(machine_image.rhel)

        with self.assertRaises(AwsMachineImage.DoesNotExist):
            AwsMachineImage.objects.get(ec2_ami_id=deleted_ami_id)

    def test_persist_aws_inspection_cluster_results_no_images(self):
        """Assert that non rhel_images are not tagged rhel."""
        ami_id = util_helper.generate_dummy_image_id()
        helper.generate_aws_image(is_encrypted=False,
                                  is_windows=False,
                                  ec2_ami_id=ami_id)

        inspection_results = {
            'cloud': 'aws',
        }

        with self.assertRaises(InvalidHoundigradeJsonFormat) as e:
            tasks.persist_aws_inspection_cluster_results(inspection_results)
            self.assertTrue(
                'Inspection results json missing images: {}'.format(
                    inspection_results) in e)

    @patch('api.tasks.aws.delete_messages_from_queue')
    @patch('api.tasks.aws.yield_messages_from_queue')
    @patch('api.tasks.aws.get_sqs_queue_url')
    @patch('api.tasks.scale_down_cluster')
    @patch('api.tasks.persist_aws_inspection_cluster_results')
    def test_persist_inspect_results_task_aws_success(
            self, mock_persist, mock_scale_down, _, mock_receive, mock_delete):
        """Assert that a valid message is correctly handled and deleted."""
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        body_dict = {
            'cloud': 'aws',
            'images': {
                'ami-12345': {
                    'rhel_found': False,
                    'drive': {
                        'partition': {
                            'evidence': [
                                {
                                    'release_file': '/centos-release',
                                    'release_file_contents': 'CentOS\n',
                                    'rhel_found': False}]}}}}}
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, json.dumps(body_dict), receipt_handle)
        mock_receive.return_value = [sqs_message]

        s, f = tasks.persist_inspection_cluster_results_task()

        mock_persist.assert_called_once_with(body_dict)
        mock_delete.assert_called_once()
        mock_scale_down.delay.assert_called_once()
        self.assertIn(sqs_message, s)
        self.assertEqual([], f)

    @patch('api.tasks.aws.delete_messages_from_queue')
    @patch('api.tasks.aws.yield_messages_from_queue')
    @patch('api.tasks.aws.get_sqs_queue_url')
    @patch('api.tasks.scale_down_cluster')
    @patch('api.tasks.persist_aws_inspection_cluster_results')
    def test_persist_inspect_results_unknown_cloud(
            self, mock_persist, mock_scale_down, _, mock_receive, mock_delete):
        """Assert message is not deleted for unknown cloud."""
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        body_dict = {'cloud': 'unknown'}
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, json.dumps(body_dict), receipt_handle)
        mock_receive.return_value = [sqs_message]

        s, f = tasks.persist_inspection_cluster_results_task()

        mock_persist.assert_not_called()
        mock_delete.assert_not_called()
        mock_scale_down.delay.assert_called_once()
        self.assertEqual([], s)
        self.assertIn(sqs_message, f)

    @patch('api.tasks.aws.delete_messages_from_queue')
    @patch('api.tasks.aws.yield_messages_from_queue')
    @patch('api.tasks.aws.get_sqs_queue_url')
    @patch('api.tasks.scale_down_cluster')
    def test_persist_inspect_results_aws_cloud_no_images(
            self, mock_scale_down, _, mock_receive, mock_delete):
        """Assert message is not deleted if it is missing images."""
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        body_dict = {'cloud': 'aws'}
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, json.dumps(body_dict), receipt_handle)
        mock_receive.return_value = [sqs_message]

        s, f = tasks.persist_inspection_cluster_results_task()

        mock_delete.assert_not_called()
        mock_scale_down.delay.assert_called_once()
        self.assertEqual([], s)
        self.assertIn(sqs_message, f)

    @patch('api.tasks.aws.delete_messages_from_queue')
    @patch('api.tasks.aws.yield_messages_from_queue')
    @patch('api.tasks.aws.get_sqs_queue_url')
    @patch('api.tasks.scale_down_cluster')
    def test_persist_inspect_results_aws_cloud_image_not_found(
            self, mock_scale_down, _, mock_receive, mock_delete):
        """
        Assert message is still deleted when our image is not found.

        See also: test_persist_aws_inspection_cluster_results_our_model_is_gone
        """
        body_dict = {'cloud': 'aws', 'images': {'fake_image': {}}}
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, json.dumps(body_dict), receipt_handle)
        mock_receive.return_value = [sqs_message]

        s, f = tasks.persist_inspection_cluster_results_task()

        mock_delete.assert_called_once()
        mock_scale_down.delay.assert_called_once()
        self.assertIn(sqs_message, s)
        self.assertEqual([], f)

    @patch('api.tasks.aws')
    def test_scale_down_cluster_success(self, mock_aws):
        """Test the scale down cluster function."""
        mock_aws.scale_down.return_value = None
        scale_down_cluster()

    def test_inspect_pending_images(self):
        """
        Test that only old "pending" images are found and reinspected.

        Note that we effectively time-travel here to points in the past to
        create the account, images, and instances. This is necessary because
        updated_at is automatically set by Django and cannot be manually set,
        but we need things with specific older updated_at times.
        """
        yesterday = timezone.now() - datetime.timedelta(days=1)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = yesterday
            account = account_helper.generate_aws_account()
            image_old_inspected = account_helper.generate_aws_image()
            image_old_pending = account_helper.generate_aws_image(
                status=MachineImage.PENDING
            )
            # an instance exists using old inspected image.
            account_helper.generate_aws_instance(
                cloud_account=account, image=image_old_inspected
            )
            # an instance exists using old pending image.
            instance_old_pending = account_helper.generate_aws_instance(
                cloud_account=account, image=image_old_pending
            )
            # another instance exists using the same old pending image, but the
            # image should still only be reinspected once regardless of how
            # many instances used it.
            account_helper.generate_aws_instance(
                cloud_account=account, image=image_old_pending
            )

        one_hour_ago = timezone.now() - datetime.timedelta(seconds=60 * 60)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = one_hour_ago
            image_new_inspected = account_helper.generate_aws_image()
            image_new_pending = account_helper.generate_aws_image(
                status=MachineImage.PENDING
            )
            # an instance exists using new inspected image.
            account_helper.generate_aws_instance(
                cloud_account=account, image=image_new_inspected
            )
            # an instance exists using new pending image, but it should not
            # trigger inspection because the image is not old enough.
            account_helper.generate_aws_instance(
                cloud_account=account, image=image_new_pending
            )

        expected_calls = [
            call(
                account.content_object.account_arn,
                image_old_pending.content_object.ec2_ami_id,
                instance_old_pending.content_object.region,
            ),
        ]
        with patch.object(tasks, 'start_image_inspection') as mock_start:
            tasks.inspect_pending_images()
            mock_start.assert_has_calls(expected_calls, any_order=True)
