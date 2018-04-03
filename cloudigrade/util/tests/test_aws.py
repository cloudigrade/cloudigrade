"""Collection of tests for ``util.aws`` module."""
import gzip
import io
import json
import uuid
from unittest.mock import patch

import boto3
import faker
from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from util import aws
from util.aws import AwsArn, InvalidArn
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
        mock_instance_id = str(uuid.uuid4())

        mock_instance = helper.generate_mock_ec2_instance(mock_instance_id)

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_session = mock_boto3.Session.return_value
            resource = mock_session.resource.return_value
            resource.Instance.return_value = mock_instance
            actual_instance = aws.get_ec2_instance(aws.get_session(mock_arn),
                                                   mock_instance_id)

        self.assertEqual(actual_instance, mock_instance)

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

    def test_receive_message_from_queue(self):
        """Assert that SQS Message objects are received."""
        mock_queue_url = 'https://123.abc'
        mock_receipt_handle = str(uuid.uuid4())
        region = settings.SQS_DEFAULT_REGION
        mock_message = boto3.resource('sqs', region_name=region)\
            .Message(mock_queue_url, mock_receipt_handle)

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.receive_messages.return_value = [mock_message]

            actual_messages = aws.receive_message_from_queue(mock_queue_url)

        self.assertEqual(mock_message, actual_messages[0])

    def test_delete_message_from_queue(self):
        """Assert that messages are deleted from SQS queue."""
        mock_queue_url = 'https://123.abc'
        mock_messages_to_delete = [
            helper.generate_mock_sqs_message(str(uuid.uuid4()),
                                             '',
                                             str(uuid.uuid4())),
            helper.generate_mock_sqs_message(str(uuid.uuid4()),
                                             '',
                                             str(uuid.uuid4()))
        ]
        mock_response = {
            'ResponseMetadata': {
                'HTTPHeaders': {
                    'connection': 'keep-alive',
                    'content-length': '1358',
                    'content-type': 'text/xml',
                    'date': 'Mon, 19 Feb 2018 20:31:09 GMT',
                    'server': 'Server',
                    'x-amzn-requestid': '1234'
                },
                'HTTPStatusCode': 200,
                'RequestId': '123456',
                'RetryAttempts': 0
            },
            'Successful': [
                {
                    'Id': 'fe3b9df2-416c-4ee2-a04e-7ba8b80490ca'
                },
                {
                    'Id': '3dc419e6-b841-48ad-ae4d-57da10a4315a'
                }
            ]
        }

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.delete_messages.return_value = mock_response

            actual_response = aws.delete_message_from_queue(
                mock_queue_url,
                mock_messages_to_delete
            )

        self.assertEqual(mock_response, actual_response)

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
