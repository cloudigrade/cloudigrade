"""Collection of tests for ``util.aws`` module."""
import gzip
import io
import json
import random
import uuid
from unittest.mock import patch

import faker
from botocore.exceptions import ClientError
from django.test import TestCase

from util import aws
from util.aws import AwsArn
from util.exceptions import (AwsSnapshotCopyLimitError,
                             AwsSnapshotNotOwnedError,
                             AwsVolumeError,
                             AwsVolumeNotReadyError,
                             InvalidArn)
from util.exceptions import SnapshotNotReadyException
from util.tests import helper


class UtilAwsTest(TestCase):
    """AWS utility functions test case."""

    def test_parse_arn_with_region_and_account(self):
        """Assert successful account ID parsing from a well-formed ARN."""
        mock_account_id = helper.generate_dummy_aws_account_id()
        mock_arn = helper.generate_dummy_arn(account_id=mock_account_id,
                                             region='test-region-1')

        arn_object = AwsArn(mock_arn)

        partition = arn_object.partition
        self.assertIsNotNone(partition)

        service = arn_object.service
        self.assertIsNotNone(service)

        region = arn_object.region
        self.assertIsNotNone(region)

        account_id = arn_object.account_id
        self.assertIsNotNone(account_id)

        resource_type = arn_object.resource_type
        self.assertIsNotNone(resource_type)

        resource_separator = arn_object.resource_separator
        self.assertIsNotNone(resource_separator)

        resource = arn_object.resource
        self.assertIsNotNone(resource)

        reconstructed_arn = 'arn:' + \
                            partition + ':' + \
                            service + ':' + \
                            region + ':' + \
                            account_id + ':' + \
                            resource_type + \
                            resource_separator + \
                            resource

        self.assertEqual(mock_account_id, account_id)
        self.assertEqual(mock_arn, reconstructed_arn)

    def test_parse_arn_without_region_or_account(self):
        """Assert successful ARN parsing without a region or an account id."""
        mock_arn = helper.generate_dummy_arn()
        arn_object = AwsArn(mock_arn)

        region = arn_object.region
        self.assertEqual(region, None)

        account_id = arn_object.account_id
        self.assertEqual(account_id, None)

    def test_parse_arn_with_slash_separator(self):
        """Assert successful ARN parsing with a slash separator."""
        mock_arn = helper.generate_dummy_arn(resource_separator='/')
        arn_object = AwsArn(mock_arn)

        resource_type = arn_object.resource_type
        self.assertIsNotNone(resource_type)

        resource_separator = arn_object.resource_separator
        self.assertEqual(resource_separator, '/')

        resource = arn_object.resource
        self.assertIsNotNone(resource)

    def test_parse_arn_with_custom_resource_type(self):
        """Assert valid ARN when resource type contains extra characters."""
        mock_arn = 'arn:aws:fakeserv:test-reg-1:012345678901:test.res type:foo'
        arn_object = AwsArn(mock_arn)

        resource_type = arn_object.resource_type
        self.assertIsNotNone(resource_type)

        resource = arn_object.resource
        self.assertIsNotNone(resource)

    def test_error_from_invalid_arn(self):
        """Assert error in account ID parsing from a badly-formed ARN."""
        mock_arn = faker.Faker().text()
        with self.assertRaises(InvalidArn):
            aws.AwsArn(mock_arn)

    def test_get_regions_with_no_args(self):
        """Assert get_regions with no args returns expected regions."""
        mock_regions = [
            f'region-{uuid.uuid4()}',
            f'region-{uuid.uuid4()}',
        ]

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_session = mock_boto3.Session.return_value
            mock_session.get_available_regions.return_value = mock_regions
            actual_regions = aws.get_regions(mock_session)
            self.assertTrue(mock_session.get_available_regions.called)
            mock_session.get_available_regions.assert_called_with('ec2')
        self.assertListEqual(mock_regions, actual_regions)

    def test_get_regions_with_custom_service(self):
        """Assert get_regions with service name returns expected regions."""
        mock_regions = [
            f'region-{uuid.uuid4()}',
            f'region-{uuid.uuid4()}',
        ]

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_session = mock_boto3.Session.return_value
            mock_session.get_available_regions.return_value = mock_regions
            actual_regions = aws.get_regions(mock_session, 'tng')
            self.assertTrue(mock_session.get_available_regions.called)
            mock_session.get_available_regions.assert_called_with('tng')
        self.assertListEqual(mock_regions, actual_regions)

    def test_get_region_from_availability_zone(self):
        """Assert that the proper region is returned for an AZ."""
        expected_region = random.choice(helper.SOME_AWS_REGIONS)
        zone = helper.generate_dummy_availability_zone(expected_region)

        az_response = {
            'AvailabilityZones': [
                {
                    'State': 'available',
                    'RegionName': expected_region,
                    'ZoneName': zone
                }
            ]
        }

        with patch.object(aws.boto3, 'client') as mock_client:
            mock_desc = mock_client.return_value.describe_availability_zones
            mock_desc.return_value = az_response

            actual_region = aws.get_region_from_availability_zone(zone)

        self.assertEqual(expected_region, actual_region)

    def test_get_session(self):
        """Assert get_session returns session object."""
        mock_arn = AwsArn(helper.generate_dummy_arn(generate_account_id=True))
        mock_account_id = mock_arn.account_id
        mock_role = helper.generate_dummy_role()

        with patch.object(aws.boto3, 'client') as mock_client:
            mock_assume_role = mock_client.return_value.assume_role
            mock_assume_role.return_value = mock_role

            session = aws.get_session(str(mock_arn))
            creds = session.get_credentials().get_frozen_credentials()

            mock_client.assert_called_with('sts')
            mock_assume_role.assert_called_with(
                Policy=json.dumps(aws.cloudigrade_policy),
                RoleArn='{0}'.format(mock_arn),
                RoleSessionName='cloudigrade-{0}'.format(mock_account_id)
            )

        self.assertEqual(creds[0], mock_role['Credentials']['AccessKeyId'])
        self.assertEqual(
            creds[1],
            mock_role['Credentials']['SecretAccessKey']
        )
        self.assertEqual(creds[2], mock_role['Credentials']['SessionToken'])

    def test_get_running_instances(self):
        """Assert we get expected instances in a dict keyed by regions."""
        mock_arn = helper.generate_dummy_arn()
        mock_regions = [f'region-{uuid.uuid4()}']
        mock_role = helper.generate_dummy_role()
        mock_running_instance = helper.generate_dummy_describe_instance(
            state=aws.InstanceState.running
        )
        mock_stopped_instance = helper.generate_dummy_describe_instance(
            state=aws.InstanceState.stopped
        )
        mock_described = {
            'Reservations': [
                {
                    'Instances': [
                        mock_running_instance,
                        mock_stopped_instance,
                    ],
                },
            ],
        }
        expected_found = {
            mock_regions[0]: [mock_running_instance]
        }

        with patch.object(aws, 'get_regions') as mock_get_regions, \
                patch.object(aws, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = mock_role
            mock_get_regions.return_value = mock_regions
            mock_client = mock_boto3.Session.return_value.client.return_value
            mock_client.describe_instances.return_value = mock_described

            actual_found = aws.get_running_instances(aws.get_session(mock_arn))

        self.assertDictEqual(expected_found, actual_found)

    def test_get_ec2_instance(self):
        """Assert that get_ec2_instance returns an instance object."""
        mock_arn = helper.generate_dummy_arn()
        mock_instance_id = helper.generate_dummy_instance_id()

        mock_instance = helper.generate_mock_ec2_instance(mock_instance_id)

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_session = mock_boto3.Session.return_value
            resource = mock_session.resource.return_value
            resource.Instance.return_value = mock_instance
            actual_instance = aws.get_ec2_instance(aws.get_session(mock_arn),
                                                   mock_instance_id)

        self.assertEqual(actual_instance, mock_instance)

    def test_get_ami(self):
        """Assert that get_ami returns an Image object."""
        mock_arn = helper.generate_dummy_arn()
        mock_region = random.choice(helper.SOME_AWS_REGIONS)
        mock_image_id = helper.generate_dummy_image_id()
        mock_image = helper.generate_mock_image(mock_image_id)

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_session = mock_boto3.Session.return_value
            resource = mock_session.resource.return_value
            resource.Image.return_value = mock_image
            actual_image = aws.get_ami(
                aws.get_session(mock_arn),
                mock_image_id,
                mock_region
            )

        self.assertEqual(actual_image, mock_image)

    def test_get_ami_snapshot_id(self):
        """Assert that an AMI returns a snapshot id."""
        mock_image_id = helper.generate_dummy_image_id()
        mock_image = helper.generate_mock_image(mock_image_id)

        expected_id = mock_image.block_device_mappings[0]['Ebs']['SnapshotId']
        actual_id = aws.get_ami_snapshot_id(mock_image)
        self.assertEqual(expected_id, actual_id)

    def test_get_snapshot(self):
        """Assert that a snapshot is returned."""
        mock_arn = helper.generate_dummy_arn()
        mock_region = random.choice(helper.SOME_AWS_REGIONS)
        mock_snapshot_id = helper.generate_dummy_snapshot_id()
        mock_snapshot = helper.generate_mock_snapshot(mock_snapshot_id)

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_session = mock_boto3.Session.return_value
            resource = mock_session.resource.return_value
            resource.Snapshot.return_value = mock_snapshot
            actual_snapshot = aws.get_snapshot(
                aws.get_session(mock_arn),
                mock_snapshot_id,
                mock_region
            )

        self.assertEqual(actual_snapshot, mock_snapshot)

    def test_add_snapshot_ownership_success(self):
        """Assert that snapshot ownership is modified."""
        mock_user_id = str(uuid.uuid4())
        mock_arn = helper.generate_dummy_arn()
        mock_region = random.choice(helper.SOME_AWS_REGIONS)
        mock_snapshot = helper.generate_mock_snapshot()

        attributes = {'CreateVolumePermissions': [{'UserId': mock_user_id}]}

        with patch.object(aws, 'boto3') as mock_boto3, \
                patch.object(aws, '_get_primary_account_id') as mock_acct_id:
            mock_acct_id.return_value = mock_user_id
            mock_session = mock_boto3.Session.return_value
            resource = mock_session.resource.return_value
            resource.Snapshot.return_value = mock_snapshot
            mock_snapshot.modify_attribute.return_value = {}
            mock_snapshot.describe_attribute.return_value = attributes
            actual_modified = aws.add_snapshot_ownership(
                aws.get_session(mock_arn),
                mock_snapshot,
                mock_region
            )

        self.assertIsNone(actual_modified)

    def test_add_snapshot_ownership_not_verified(self):
        """Assert an error is raised when ownership is not verified."""
        mock_user_id = str(uuid.uuid4())
        mock_arn = helper.generate_dummy_arn()
        mock_region = random.choice(helper.SOME_AWS_REGIONS)
        mock_snapshot = helper.generate_mock_snapshot()

        attributes = {'CreateVolumePermissions': []}

        with patch.object(aws, 'boto3') as mock_boto3, \
                patch.object(aws, '_get_primary_account_id') as mock_acct_id:
            mock_acct_id.return_value = mock_user_id
            mock_session = mock_boto3.Session.return_value
            resource = mock_session.resource.return_value
            resource.Snapshot.return_value = mock_snapshot
            mock_snapshot.modify_attribute.return_value = {}
            mock_snapshot.describe_attribute.return_value = attributes
            with self.assertRaises(AwsSnapshotNotOwnedError):
                aws.add_snapshot_ownership(
                    aws.get_session(mock_arn),
                    mock_snapshot,
                    mock_region
                )

    def test_copy_snapshot_success(self):
        """Assert that a snapshot copy operation begins."""
        mock_region = random.choice(helper.SOME_AWS_REGIONS)
        mock_snapshot = helper.generate_mock_snapshot()
        mock_copied_snapshot_id = helper.generate_dummy_snapshot_id()
        mock_copy_result = {'SnapshotId': mock_copied_snapshot_id}

        with patch.object(aws, 'boto3') as mock_boto3:
            resource = mock_boto3.resource.return_value
            resource.Snapshot.return_value = mock_snapshot
            mock_snapshot.copy.return_value = mock_copy_result

            actual_copied_snapshot_id = aws.copy_snapshot(
                mock_snapshot.snapshot_id,
                mock_region
            )

        self.assertEqual(actual_copied_snapshot_id, mock_copied_snapshot_id)

    def test_copy_snapshot_limit_reached(self):
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

        with patch.object(aws, 'boto3') as mock_boto3:
            resource = mock_boto3.resource.return_value
            resource.Snapshot.return_value = mock_snapshot
            mock_snapshot.copy.side_effect = ClientError(
                mock_copy_error, 'CopySnapshot')

            with self.assertRaises(AwsSnapshotCopyLimitError):
                aws.copy_snapshot(
                    mock_snapshot.snapshot_id,
                    mock_region
                )

    def test_copy_snapshot_failure(self):
        """Assert that an error is given when copy fails."""
        mock_region = random.choice(helper.SOME_AWS_REGIONS)
        mock_snapshot = helper.generate_mock_snapshot()

        mock_copy_error = {
            'Error': {
                'Code': 'MockError',
                'Message': 'The operation failed.'
            }
        }

        with patch.object(aws, 'boto3') as mock_boto3:
            resource = mock_boto3.resource.return_value
            resource.Snapshot.return_value = mock_snapshot
            mock_snapshot.copy.side_effect = ClientError(
                mock_copy_error, 'CopySnapshot')

            with self.assertRaises(ClientError):
                aws.copy_snapshot(
                    mock_snapshot.snapshot_id,
                    mock_region
                )

    def test_verify_account_access_success(self):
        """Assert that account access via a IAM role is verified."""
        mock_arn = helper.generate_dummy_arn()
        mock_role = helper.generate_dummy_role()
        mock_dry_run_exception = {
            'Error': {
                'Code': 'DryRunOperation',
                'Message': 'Request would have succeeded, '
                           'but DryRun flag is set.'
            }
        }
        with patch.object(aws, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = mock_role

            mock_client = mock_boto3.Session.return_value.client.return_value
            mock_describe_images = mock_client.describe_images
            mock_describe_instances = mock_client.describe_instances
            mock_describe_snapshot_attribute = \
                mock_client.describe_snapshot_attribute
            mock_describe_snapshots = mock_client.describe_snapshots
            mock_modify_snapshot_attribute = \
                mock_client.modify_snapshot_attribute
            mock_modify_image_attribute = mock_client.modify_image_attribute

            mock_describe_images.side_effect = ClientError(
                mock_dry_run_exception, 'DescribeImages')
            mock_describe_instances.side_effect = ClientError(
                mock_dry_run_exception, 'DescribeInstances')
            mock_describe_snapshot_attribute.side_effect = ClientError(
                mock_dry_run_exception, 'DescribeSnapshotAttribute')
            mock_describe_snapshots.side_effect = ClientError(
                mock_dry_run_exception, 'DescribeSnapshots')
            mock_modify_snapshot_attribute.side_effect = ClientError(
                mock_dry_run_exception, 'ModifySnapshotAttribute')
            mock_modify_image_attribute.side_effect = ClientError(
                mock_dry_run_exception, 'ModifyImageAttribute')

            actual_verified = aws.verify_account_access(
                aws.get_session(mock_arn))

            mock_describe_images.assert_called_with(DryRun=True)
            mock_describe_instances.assert_called_with(DryRun=True)
            mock_describe_snapshot_attribute.assert_called_with(
                DryRun=True,
                SnapshotId=aws.SNAPSHOT_ID,
                Attribute='productCodes'
            )
            mock_describe_snapshots.assert_called_with(DryRun=True)
            mock_modify_snapshot_attribute.assert_called_with(
                SnapshotId=aws.SNAPSHOT_ID,
                DryRun=True,
                Attribute='createVolumePermission',
                OperationType='add'
            )
            mock_modify_image_attribute.assert_called_with(
                Attribute='description',
                ImageId='string',
                DryRun=True
            )

        self.assertTrue(actual_verified)

    def test_verify_account_access_failure(self):
        """Assert that account access via a IAM role is not verified."""
        mock_arn = helper.generate_dummy_arn()
        mock_role = helper.generate_dummy_role()
        mock_unauthorized_exception = {
            'Error': {
                'Code': 'UnauthorizedOperation',
                'Message': 'You are not authorized '
                           'to perform this operation.'
            }
        }
        mock_garbage_exception = {
            'Error': {
                'Code': 'GarbageOperation',
                'Message': 'You are not authorized '
                           'to perform this garbage operation.'
            }
        }
        bad_policy = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Sid': 'CloudigradeGarbagePolicy',
                    'Effect': 'Allow',
                    'Action': [
                        'ec2:DescribeGarbage'
                    ],
                    'Resource': '*'
                }
            ]
        }

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = mock_role

            mock_client = mock_boto3.Session.return_value.client.return_value
            mock_describe_images = mock_client.describe_images
            mock_describe_instances = mock_client.describe_instances
            mock_describe_snapshot_attribute = \
                mock_client.describe_snapshot_attribute
            mock_describe_snapshots = mock_client.describe_snapshots
            mock_modify_snapshot_attribute = \
                mock_client.modify_snapshot_attribute
            mock_modify_image_attribute = mock_client.modify_image_attribute

            mock_describe_images.side_effect = ClientError(
                mock_unauthorized_exception, 'DescribeImages')
            mock_describe_instances.side_effect = ClientError(
                mock_unauthorized_exception, 'DescribeInstances')
            mock_describe_snapshot_attribute.side_effect = ClientError(
                mock_unauthorized_exception, 'DescribeSnapshotAttribute')
            mock_describe_snapshots.side_effect = ClientError(
                mock_unauthorized_exception, 'DescribeSnapshots')
            mock_modify_snapshot_attribute.side_effect = ClientError(
                mock_unauthorized_exception, 'ModifySnapshotAttribute')
            mock_modify_image_attribute.side_effect = ClientError(
                mock_unauthorized_exception, 'ModifyImageAttribute')

            session = aws.get_session(mock_arn)
            actual_verified = aws.verify_account_access(session)

            mock_describe_images.side_effect = ClientError(
                mock_garbage_exception, 'DescribeImages')

            with self.assertRaises(ClientError) as e:
                aws.verify_account_access(session)

            self.assertEqual(e.exception.response['Error']['Code'],
                             mock_garbage_exception['Error']['Code'])
            self.assertEqual(e.exception.response['Error']['Message'],
                             mock_garbage_exception['Error']['Message'])

            with patch.dict(aws.cloudigrade_policy, bad_policy):
                aws.verify_account_access(session)

            mock_describe_images.assert_called_with(DryRun=True)
            mock_describe_instances.assert_called_with(DryRun=True)
            mock_describe_snapshot_attribute.assert_called_with(
                DryRun=True,
                SnapshotId=aws.SNAPSHOT_ID,
                Attribute='productCodes'
            )
            mock_describe_snapshots.assert_called_with(DryRun=True)
            mock_modify_snapshot_attribute.assert_called_with(
                SnapshotId=aws.SNAPSHOT_ID,
                DryRun=True,
                Attribute='createVolumePermission',
                OperationType='add',
            )
            mock_modify_image_attribute.assert_called_with(
                Attribute='description',
                ImageId='string',
                DryRun=True
            )

        self.assertFalse(actual_verified)

    def test_get_object_content_from_s3_gzipped(self):
        """Assert that gzipped content is handled."""
        mock_bucket = 'test_bucket'
        mock_key = '/path/to/file'
        mock_content_bytes = b'{"Key": "Value"}'
        mock_byte_stream = io.BytesIO(gzip.compress(mock_content_bytes))
        mock_object_body = {'Body': mock_byte_stream}

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_s3_object = mock_resource.Object.return_value
            mock_s3_object.get.return_value = mock_object_body

            actual_content = aws.get_object_content_from_s3(
                mock_bucket,
                mock_key
            )

        self.assertEqual(mock_content_bytes.decode('utf-8'), actual_content)

    def test_get_object_content_from_s3_uncompressed(self):
        """Assert that uncompressed content is handled."""
        mock_bucket = 'test_bucket'
        mock_key = '/path/to/file'
        mock_content_bytes = b'{"Key": "Value"}'
        mock_byte_stream = io.BytesIO(mock_content_bytes)
        mock_object_body = {'Body': mock_byte_stream}

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_s3_object = mock_resource.Object.return_value
            mock_s3_object.get.return_value = mock_object_body

            actual_content = aws.get_object_content_from_s3(
                mock_bucket,
                mock_key,
                compression=None
            )

        self.assertEqual(mock_content_bytes.decode('utf-8'), actual_content)

    def test_get_object_content_from_s3_unsupported_compression(self):
        """Assert that unhandled compression does not return content."""
        mock_bucket = 'test_bucket'
        mock_key = '/path/to/file'
        mock_content_bytes = b'{"Key": "Value"}'
        mock_byte_stream = io.BytesIO(mock_content_bytes)
        mock_object_body = {'Body': mock_byte_stream}

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_s3_object = mock_resource.Object.return_value
            mock_s3_object.get.return_value = mock_object_body

            actual_content = aws.get_object_content_from_s3(
                mock_bucket,
                mock_key,
                compression='bzip'
            )

        self.assertIsNone(actual_content)

    @patch('util.aws.boto3')
    def test_create_volume_snapshot_ready(self, mock_boto3):
        """Test that volume creation starts when snapshot is ready."""
        zone = helper.generate_dummy_availability_zone()
        mock_snapshot = helper.generate_mock_snapshot()
        mock_volume = helper.generate_mock_volume()

        mock_ec2 = mock_boto3.resource.return_value
        mock_ec2.Snapshot.return_value = mock_snapshot
        mock_ec2.create_volume.return_value = mock_volume

        volume_id = aws.create_volume(mock_snapshot.snapshot_id, zone)

        mock_ec2.create_volume.assert_called_with(
            SnapshotId=mock_snapshot.snapshot_id,
            AvailabilityZone=zone)

        mock_boto3.resource.assert_called_once_with('ec2')
        self.assertEqual(volume_id, mock_volume.id)

    @patch('util.aws.boto3')
    def test_create_volume_snapshot_not_ready(self, mock_boto3):
        """Test that volume creation aborts when snapshot is not ready."""
        zone = helper.generate_dummy_availability_zone()
        mock_snapshot = helper.generate_mock_snapshot(state='pending')

        mock_ec2 = mock_boto3.resource.return_value
        mock_ec2.Snapshot.return_value = mock_snapshot

        with self.assertRaises(SnapshotNotReadyException):
            aws.create_volume(mock_snapshot.snapshot_id, zone)

        mock_boto3.resource.assert_called_once_with('ec2')
        mock_ec2.create_volume.assert_not_called()

    @patch('util.aws.boto3')
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
        actual_volume = aws.get_volume(volume_id, region)

        self.assertEqual(actual_volume, mock_volume)

    def test_check_volume_state_available(self):
        """Test that a volume is available."""
        mock_volume = helper.generate_mock_volume(state='available')
        self.assertIsNone(aws.check_volume_state(mock_volume))

    def test_check_volume_state_creating(self):
        """Test the appropriate error for still creating volumes."""
        mock_volume = helper.generate_mock_volume(state='creating')
        with self.assertRaises(AwsVolumeNotReadyError):
            aws.check_volume_state(mock_volume)

    def test_check_volume_state_error(self):
        """Test the appropriate error for other volume states."""
        mock_volume = helper.generate_mock_volume(state='error')
        with self.assertRaises(AwsVolumeError):
            aws.check_volume_state(mock_volume)
