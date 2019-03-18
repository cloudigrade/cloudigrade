"""Collection of tests for ``util.aws.ec2`` module."""
import random
import uuid
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.test import TestCase

from util.aws import ec2
from util.exceptions import (AwsImageError,
                             AwsSnapshotCopyLimitError,
                             AwsSnapshotError,
                             AwsSnapshotNotOwnedError,
                             AwsSnapshotOwnedError,
                             AwsVolumeError,
                             AwsVolumeNotReadyError,
                             ImageNotReadyException,
                             SnapshotNotReadyException)
from util.tests import helper


class UtilAwsEc2Test(TestCase):
    """AWS EC2 utility functions test case."""

    def test_get_all_instances(self):
        """
        Assert we get expected instances in a dict keyed by regions.

        The setup here is a little complicated, and it's important to
        understand what's going into it. The mock response from the client's
        `describe_instances` includes a Reservations list of **three** elements
        with different Instances in each. It is unclear to us how AWS divides
        Instances into Reservations; so, we must ensure in our tests that we
        are checking for Instances in potentially multiple Reservations.
        """
        mock_regions = [f'region-{uuid.uuid4()}']
        mock_role = helper.generate_dummy_role()

        mock_session = Mock()
        mock_assume_role = mock_session.client.return_value.assume_role
        mock_assume_role.return_value = mock_role

        mock_running_instance_1 = helper.generate_dummy_describe_instance(
            state=ec2.InstanceState.running
        )
        mock_running_instance_2 = helper.generate_dummy_describe_instance(
            state=ec2.InstanceState.running
        )
        mock_stopped_instance_1 = helper.generate_dummy_describe_instance(
            state=ec2.InstanceState.stopped
        )
        mock_stopped_instance_2 = helper.generate_dummy_describe_instance(
            state=ec2.InstanceState.stopped
        )
        mock_described = {
            'Reservations': [
                {
                    'Instances': [
                        mock_running_instance_1,
                        mock_stopped_instance_1,
                    ],
                },
                {
                    'Instances': [
                        mock_running_instance_2,
                    ],
                },
                {
                    'Instances': [
                        mock_stopped_instance_2,
                    ],
                },
            ],
        }

        mock_client = mock_session.client.return_value
        mock_client.describe_instances.return_value = mock_described

        expected_found = {
            mock_regions[0]: [
                mock_running_instance_1,
                mock_stopped_instance_1,
                mock_running_instance_2,
                mock_stopped_instance_2,
            ]
        }

        with patch.object(ec2, 'get_regions') as mock_get_regions:
            mock_get_regions.return_value = mock_regions
            actual_found = ec2.get_all_instances(mock_session)

        self.assertDictEqual(expected_found, actual_found)

    def test_get_ec2_instance(self):
        """Assert that get_ec2_instance returns an Instance."""
        mock_instance_id = helper.generate_dummy_instance_id()
        mock_instance = helper.generate_mock_ec2_instance(mock_instance_id)

        mock_session = Mock()
        mock_resource = mock_session.resource.return_value
        mock_resource.Instance.return_value = mock_instance

        actual_instance = ec2.get_ec2_instance(mock_session, mock_instance_id)
        self.assertEqual(actual_instance, mock_instance)

        mock_session.resource.assert_called_once_with('ec2')
        mock_resource.Instance.assert_called_once_with(mock_instance_id)

    @patch('util.aws.ec2.check_image_state')
    def test_get_ami(self, mock_check_image_state):
        """Assert that get_ami returns an Image."""
        mock_image_id = helper.generate_dummy_image_id()
        mock_image = helper.generate_mock_image(mock_image_id)

        mock_session = Mock()
        mock_resource = mock_session.resource.return_value
        mock_resource.Image.return_value = mock_image

        mock_region = random.choice(helper.SOME_AWS_REGIONS)

        actual_image = ec2.get_ami(mock_session, mock_image_id, mock_region)
        self.assertEqual(actual_image, mock_image)

        mock_session.resource.assert_called_once_with('ec2',
                                                      region_name=mock_region)
        mock_resource.Image.assert_called_once_with(mock_image_id)
        mock_check_image_state.assert_called_once_with(mock_image)

    def test_check_image_state_available(self):
        """Assert clean return when image state is available."""
        mock_image = helper.generate_mock_image(state='available')
        ec2.check_image_state(mock_image)

    def test_check_image_state_failed(self):
        """Assert raised exception when image state is failed."""
        mock_image = helper.generate_mock_image(state='failed')
        with self.assertRaises(AwsImageError):
            ec2.check_image_state(mock_image)

    def test_check_image_state_unhandled(self):
        """Assert raised exception when image state is unhandled."""
        mock_image = helper.generate_mock_image(state='itisamystery.gif')
        with self.assertRaises(ImageNotReadyException):
            ec2.check_image_state(mock_image)

    def test_check_image_state_no_meta(self):
        """Assert raised exception when image has no metadata."""
        mock_image = helper.generate_mock_image()
        mock_image.meta.data = None
        with self.assertRaises(AwsImageError):
            ec2.check_image_state(mock_image)

    def test_get_ami_snapshot_id(self):
        """Assert that an AMI returns a snapshot id."""
        mock_image_id = helper.generate_dummy_image_id()
        mock_image = helper.generate_mock_image(mock_image_id)

        expected_id = mock_image.block_device_mappings[0]['Ebs']['SnapshotId']
        actual_id = ec2.get_ami_snapshot_id(mock_image)
        self.assertEqual(expected_id, actual_id)

    def test_get_snapshot(self):
        """Assert that get_snapshot returns a Snapshot."""
        mock_snapshot_id = helper.generate_dummy_snapshot_id()
        mock_snapshot = helper.generate_mock_snapshot(mock_snapshot_id)

        mock_session = Mock()
        mock_resource = mock_session.resource.return_value
        mock_resource.Snapshot.return_value = mock_snapshot

        mock_region = random.choice(helper.SOME_AWS_REGIONS)

        actual_snapshot = ec2.get_snapshot(mock_session, mock_snapshot_id,
                                           mock_region)
        self.assertEqual(actual_snapshot, mock_snapshot)

        mock_session.resource.assert_called_once_with('ec2',
                                                      region_name=mock_region)
        mock_resource.Snapshot.assert_called_once_with(mock_snapshot_id)

    def test_add_snapshot_ownership_success(self):
        """Assert that snapshot ownership is modified successfully."""
        mock_user_id = str(uuid.uuid4())

        mock_snapshot = helper.generate_mock_snapshot()
        mock_snapshot.describe_attribute.return_value = {
            'CreateVolumePermissions': [{'UserId': mock_user_id}],
        }

        with patch.object(ec2, '_get_primary_account_id') as mock_get_acct_id:
            mock_get_acct_id.return_value = mock_user_id
            actual_modified = ec2.add_snapshot_ownership(mock_snapshot)

        self.assertIsNone(actual_modified)

        expected_permission = {'Add': [{'UserId': mock_user_id}]}
        expected_user_ids = [mock_user_id]
        mock_snapshot.modify_attribute.assert_called_once_with(
            Attribute='createVolumePermission',
            CreateVolumePermission=expected_permission,
            OperationType='add',
            UserIds=expected_user_ids
        )
        mock_snapshot.describe_attribute.assert_called_once_with(
            Attribute='createVolumePermission'
        )

    def test_add_snapshot_ownership_not_verified(self):
        """Assert an error is raised when ownership is not verified."""
        mock_user_id = str(uuid.uuid4())

        mock_snapshot = helper.generate_mock_snapshot()
        mock_snapshot.describe_attribute.return_value = {
            'CreateVolumePermissions': [],
        }

        with patch.object(ec2, '_get_primary_account_id') as mock_get_acct_id:
            mock_get_acct_id.return_value = mock_user_id
            with self.assertRaises(AwsSnapshotNotOwnedError):
                ec2.add_snapshot_ownership(mock_snapshot)

        expected_permission = {'Add': [{'UserId': mock_user_id}]}
        expected_user_ids = [mock_user_id]
        mock_snapshot.modify_attribute.assert_called_once_with(
            Attribute='createVolumePermission',
            CreateVolumePermission=expected_permission,
            OperationType='add',
            UserIds=expected_user_ids
        )
        mock_snapshot.describe_attribute.assert_called_once_with(
            Attribute='createVolumePermission'
        )

    def test_remove_snapshot_ownership_success(self):
        """Assert that snapshot ownership is removed successfully."""
        mock_user_id = str(uuid.uuid4())

        mock_snapshot = helper.generate_mock_snapshot()
        mock_snapshot.describe_attribute.return_value = {
            'CreateVolumePermissions': [],
        }

        with patch.object(ec2, '_get_primary_account_id') as mock_get_acct_id:
            mock_get_acct_id.return_value = mock_user_id
            actual_modified = ec2.remove_snapshot_ownership(mock_snapshot)

        self.assertIsNone(actual_modified)

        expected_permission = {'Remove': [{'UserId': mock_user_id}]}
        expected_user_ids = [mock_user_id]
        mock_snapshot.modify_attribute.assert_called_once_with(
            Attribute='createVolumePermission',
            CreateVolumePermission=expected_permission,
            OperationType='remove',
            UserIds=expected_user_ids
        )
        mock_snapshot.describe_attribute.assert_called_once_with(
            Attribute='createVolumePermission'
        )

    def test_remove_snapshot_ownership_not_verified(self):
        """Assert an error is raised when ownership is not removed."""
        mock_user_id = str(uuid.uuid4())

        mock_snapshot = helper.generate_mock_snapshot()
        mock_snapshot.describe_attribute.return_value = {
            'CreateVolumePermissions': [{'UserId': mock_user_id}],
        }

        with patch.object(ec2, '_get_primary_account_id') as mock_get_acct_id:
            mock_get_acct_id.return_value = mock_user_id
            with self.assertRaises(AwsSnapshotOwnedError):
                ec2.remove_snapshot_ownership(mock_snapshot)

        expected_permission = {'Remove': [{'UserId': mock_user_id}]}
        expected_user_ids = [mock_user_id]
        mock_snapshot.modify_attribute.assert_called_once_with(
            Attribute='createVolumePermission',
            CreateVolumePermission=expected_permission,
            OperationType='remove',
            UserIds=expected_user_ids
        )
        mock_snapshot.describe_attribute.assert_called_once_with(
            Attribute='createVolumePermission'
        )

    def test_remove_snapshot_ownership_other_user(self):
        """Assert an error is not raised when other user has ownership."""
        mock_user_id = str(uuid.uuid4())

        mock_snapshot = helper.generate_mock_snapshot()
        mock_snapshot.describe_attribute.return_value = {
            'CreateVolumePermissions': [{'UserId': 'mock_user_id'}],
        }

        with patch.object(ec2, '_get_primary_account_id') as mock_get_acct_id:
            mock_get_acct_id.return_value = mock_user_id
            ec2.remove_snapshot_ownership(mock_snapshot)

        expected_permission = {'Remove': [{'UserId': mock_user_id}]}
        expected_user_ids = [mock_user_id]
        mock_snapshot.modify_attribute.assert_called_once_with(
            Attribute='createVolumePermission',
            CreateVolumePermission=expected_permission,
            OperationType='remove',
            UserIds=expected_user_ids
        )
        mock_snapshot.describe_attribute.assert_called_once_with(
            Attribute='createVolumePermission'
        )

    @patch('util.aws.ec2.boto3')
    def test_copy_snapshot_success(self, mock_boto3):
        """Assert that a snapshot copy operation begins."""
        mock_region = random.choice(helper.SOME_AWS_REGIONS)
        mock_snapshot = helper.generate_mock_snapshot()
        mock_copied_snapshot_id = helper.generate_dummy_snapshot_id()
        mock_copy_result = {'SnapshotId': mock_copied_snapshot_id}

        resource = mock_boto3.resource.return_value
        resource.Snapshot.return_value = mock_snapshot
        mock_snapshot.copy.return_value = mock_copy_result

        actual_copied_snapshot_id = ec2.copy_snapshot(
            mock_snapshot.snapshot_id,
            mock_region
        )
        self.assertEqual(actual_copied_snapshot_id, mock_copied_snapshot_id)

    @patch('util.aws.ec2.boto3')
    def test_copy_snapshot_limit_reached(self, mock_boto3):
        """Assert that an error is returned when the copy limit is reached."""
        mock_region = random.choice(helper.SOME_AWS_REGIONS)
        mock_snapshot = helper.generate_mock_snapshot()

        mock_copy_error = {
            'Error': {
                'Code': 'ResourceLimitExceeded',
                'Message': 'You have exceeded an Amazon EC2 resource limit. '
                           'For example, you might have too many snapshot '
                           'copies in progress.'
            }
        }

        resource = mock_boto3.resource.return_value
        resource.Snapshot.return_value = mock_snapshot
        mock_snapshot.copy.side_effect = ClientError(
            mock_copy_error, 'CopySnapshot')

        with self.assertRaises(AwsSnapshotCopyLimitError):
            ec2.copy_snapshot(
                mock_snapshot.snapshot_id,
                mock_region
            )

    @patch('util.aws.ec2.boto3')
    def test_copy_snapshot_failure(self, mock_boto3):
        """Assert that an error is given when copy fails."""
        mock_region = random.choice(helper.SOME_AWS_REGIONS)
        mock_snapshot = helper.generate_mock_snapshot()

        mock_copy_error = {
            'Error': {
                'Code': 'MockError',
                'Message': 'The operation failed.'
            }
        }

        resource = mock_boto3.resource.return_value
        resource.Snapshot.return_value = mock_snapshot
        mock_snapshot.copy.side_effect = ClientError(
            mock_copy_error, 'CopySnapshot')

        with self.assertRaises(ClientError):
            ec2.copy_snapshot(
                mock_snapshot.snapshot_id,
                mock_region
            )

    @patch('util.aws.ec2.boto3')
    def test_create_volume_snapshot_ready(self, mock_boto3):
        """Test that volume creation starts when snapshot is ready."""
        zone = helper.generate_dummy_availability_zone()
        mock_snapshot = helper.generate_mock_snapshot()
        mock_volume = helper.generate_mock_volume()

        mock_ec2 = mock_boto3.resource.return_value
        mock_ec2.Snapshot.return_value = mock_snapshot
        mock_ec2.create_volume.return_value = mock_volume

        volume_id = ec2.create_volume(mock_snapshot.snapshot_id, zone)

        mock_ec2.create_volume.assert_called_with(
            SnapshotId=mock_snapshot.snapshot_id,
            AvailabilityZone=zone)

        mock_boto3.resource.assert_called_once_with('ec2')
        self.assertEqual(volume_id, mock_volume.id)

    @patch('util.aws.ec2.boto3')
    def test_create_volume_snapshot_not_ready(self, mock_boto3):
        """Test that volume creation aborts when snapshot is not ready."""
        zone = helper.generate_dummy_availability_zone()
        mock_snapshot = helper.generate_mock_snapshot(state='pending')

        mock_ec2 = mock_boto3.resource.return_value
        mock_ec2.Snapshot.return_value = mock_snapshot

        with self.assertRaises(SnapshotNotReadyException):
            ec2.create_volume(mock_snapshot.snapshot_id, zone)

        mock_boto3.resource.assert_called_once_with('ec2')
        mock_ec2.create_volume.assert_not_called()

    @patch('util.aws.ec2.boto3')
    def test_create_volume_snapshot_has_error(self, mock_boto3):
        """Test that volume creation aborts when snapshot has error."""
        zone = helper.generate_dummy_availability_zone()
        mock_snapshot = helper.generate_mock_snapshot(state='error')

        mock_ec2 = mock_boto3.resource.return_value
        mock_ec2.Snapshot.return_value = mock_snapshot

        with self.assertRaises(AwsSnapshotError):
            ec2.create_volume(mock_snapshot.snapshot_id, zone)

        mock_boto3.resource.assert_called_once_with('ec2')
        mock_ec2.create_volume.assert_not_called()

    @patch('util.aws.ec2.boto3')
    def test_get_volume(self, mock_boto3):
        """Test that a Volume is returned."""
        region = random.choice(helper.SOME_AWS_REGIONS)
        zone = helper.generate_dummy_availability_zone(region)
        volume_id = helper.generate_dummy_volume_id()
        mock_volume = helper.generate_mock_volume(
            volume_id=volume_id,
            zone=zone
        )

        resource = mock_boto3.resource.return_value
        resource.Volume.return_value = mock_volume
        actual_volume = ec2.get_volume(volume_id, region)

        self.assertEqual(actual_volume, mock_volume)

    def test_check_volume_state_available(self):
        """Test that a volue is available."""
        mock_volume = helper.generate_mock_volume(state='available')
        self.assertIsNone(ec2.check_volume_state(mock_volume))

    def test_check_volume_state_creating(self):
        """Test the appropriate error for still creating volumes."""
        mock_volume = helper.generate_mock_volume(state='creating')
        with self.assertRaises(AwsVolumeNotReadyError):
            ec2.check_volume_state(mock_volume)

    def test_check_volume_state_error(self):
        """Test the appropriate error for other volume states."""
        mock_volume = helper.generate_mock_volume(state='error')
        with self.assertRaises(AwsVolumeError):
            ec2.check_volume_state(mock_volume)

    def test_is_windows_lowercase(self):
        """Test that an instance with Platform 'windows' is windows."""
        dummy_instance = helper.generate_dummy_describe_instance(
            platform='windows'
        )
        self.assertTrue(ec2.is_windows(dummy_instance))

    def test_is_windows_with_unexpected_case(self):
        """Test that an instance with Platform 'WiNdOwS' is windows."""
        dummy_instance = helper.generate_dummy_describe_instance(
            platform='WiNdOwS'
        )
        self.assertTrue(ec2.is_windows(dummy_instance))

    def test_is_windows_with_empty_platform(self):
        """Test that an instance with no Platform is not windows."""
        dummy_instance = helper.generate_dummy_describe_instance()
        self.assertFalse(ec2.is_windows(dummy_instance))

    def test_is_windows_with_other_platform(self):
        """Test that an instance with Platform 'other' is not windows."""
        dummy_instance = helper.generate_dummy_describe_instance(
            platform='other'
        )
        self.assertFalse(ec2.is_windows(dummy_instance))

    def test_copy_ami(self):
        """Test that an image is copied via the boto session successfully."""
        mock_session = Mock()
        mock_ec2_client = mock_session.client.return_value
        mock_original_image = Mock()
        mock_copied_image_dict = helper.generate_mock_image_dict()
        mock_ec2_client.copy_image.return_value = mock_copied_image_dict

        image_id = mock_original_image.id
        source_region = random.choice(helper.SOME_AWS_REGIONS)
        with patch.object(ec2, 'get_ami') as mock_get_ami:
            mock_get_ami.return_value = mock_original_image
            result = ec2.copy_ami(mock_session, image_id, source_region)

        mock_ec2_client.copy_image.assert_called_once()
        mock_ec2_client.create_tags.assert_called_once()
        self.assertEqual(result, mock_copied_image_dict['ImageId'])
