"""Collection of tests for ``util.aws`` module."""
import gzip
import io
import uuid
from unittest.mock import Mock
from unittest.mock import patch

import boto3
from botocore.exceptions import ClientError
import faker
from django.test import TestCase

from util import aws
from util.tests import helper


class UtilAwsTest(TestCase):
    """AWS utility functions test case."""

    def test_extract_account_id_from_arn(self):
        """Assert successful account ID extraction from a well-formed ARN."""
        mock_account_id = helper.generate_dummy_aws_account_id()
        mock_arn = helper.generate_dummy_arn(mock_account_id)
        extracted_account_id = aws.extract_account_id_from_arn(mock_arn)
        self.assertEqual(mock_account_id, extracted_account_id)

    def test_error_extract_account_id_from_invalid_arn(self):
        """Assert error in account ID extraction from a badly-formed ARN."""
        mock_arn = faker.Faker().text()
        with self.assertRaises(Exception):  # TODO more specific exceptions
            aws.extract_account_id_from_arn(mock_arn)

    def test_get_regions_with_no_args(self):
        """Assert get_regions with no args returns expected regions."""
        mock_regions = [
            f'region-{uuid.uuid4()}',
            f'region-{uuid.uuid4()}',
        ]

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_session = mock_boto3.Session.return_value
            mock_session.get_available_regions.return_value = mock_regions
            actual_regions = aws.get_regions()
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
            actual_regions = aws.get_regions('tng')
            self.assertTrue(mock_session.get_available_regions.called)
            mock_session.get_available_regions.assert_called_with('tng')
        self.assertListEqual(mock_regions, actual_regions)

    def test_get_credentials_for_arn(self):
        """Assert get_credentials_for_arn returns credentials dict."""
        mock_arn = helper.generate_dummy_arn()
        mock_role = {
            'Credentials': {
                'AccessKeyId': str(uuid.uuid4()),
                'SecretAccessKey': str(uuid.uuid4()),
                'SessionToken': str(uuid.uuid4()),
            },
            'foo': 'bar',
        }

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_client = mock_boto3.client.return_value
            mock_assume_role = mock_client.assume_role
            mock_assume_role.return_value = mock_role

            actual_credentials = aws.get_credentials_for_arn(mock_arn)

            mock_boto3.client.assert_called_with('sts')
            mock_assume_role.assert_called_with(RoleArn=mock_arn,
                                                RoleSessionName='temp-session')

        self.assertDictEqual(mock_role['Credentials'], actual_credentials)

    def test_get_running_instances(self):
        """Assert we get expected instances in a dict keyed by regions."""
        mock_arn = helper.generate_dummy_arn()
        mock_regions = [f'region-{uuid.uuid4()}']
        mock_credentials = {
            'AccessKeyId': str(uuid.uuid4()),
            'SecretAccessKey': str(uuid.uuid4()),
            'SessionToken': str(uuid.uuid4()),
        }
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

        with patch.object(aws, 'get_credentials_for_arn') as mock_get_creds, \
                patch.object(aws, 'get_regions') as mock_get_regions, \
                patch.object(aws, 'boto3') as mock_boto3:
            mock_get_creds.return_value = mock_credentials
            mock_get_regions.return_value = mock_regions
            mock_client = mock_boto3.Session.return_value.client.return_value
            mock_client.describe_instances.return_value = mock_described

            actual_found = aws.get_running_instances(mock_arn)

        self.assertDictEqual(expected_found, actual_found)

    def test_verify_account_access_success(self):
        """Assert that account access via a IAM role is verified."""
        mock_arn = helper.generate_dummy_arn()
        mock_credentials = {
            'AccessKeyId': str(uuid.uuid4()),
            'SecretAccessKey': str(uuid.uuid4()),
            'SessionToken': str(uuid.uuid4()),
        }

        with patch.object(aws, 'get_credentials_for_arn') as mock_get_creds, \
                patch.object(aws, 'boto3') as __:  # noqa: F841
            mock_get_creds.return_value = mock_credentials

            actual_verified = aws.verify_account_access(mock_arn)

        self.assertTrue(actual_verified)

    def test_verify_account_access_failure(self):
        """Assert that account access via a IAM role is not verified."""
        mock_arn = helper.generate_dummy_arn()
        mock_credentials = {
            'AccessKeyId': str(uuid.uuid4()),
            'SecretAccessKey': str(uuid.uuid4()),
            'SessionToken': str(uuid.uuid4()),
        }
        errmsg = f'User: {mock_arn} is not authorized to perform: ' + \
            'ec2:DescribeInstances'
        error_response = {
            'Error': {
                'Message': errmsg,
                'Code': 'AccessDeniedException'
            }
        }
        operation_name = 'DescribeInstances'

        with patch.object(aws, 'get_credentials_for_arn') as mock_get_creds, \
                patch.object(aws, 'boto3') as mock_boto3:
            mock_get_creds.return_value = mock_credentials
            mock_client = mock_boto3.Session.return_value.client.return_value
            mock_client.describe_instances.side_effect = ClientError(
                error_response,
                operation_name)

            actual_verified = aws.verify_account_access(mock_arn)

        self.assertFalse(actual_verified)

    def test_receive_message_from_queue(self):
        """Assert that SQS Message objects are received."""
        mock_queue_url = 'https://123.abc'
        mock_receipt_handle = str(uuid.uuid4())
        mock_message = boto3.resource('sqs').Message(mock_queue_url,
                                                     mock_receipt_handle)
        mock_message

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.receive_messages.return_value = [mock_message]

            actual_messages = aws.receive_message_from_queue(mock_queue_url)

        self.assertEqual(mock_message, actual_messages[0])

    def test_delete_message_from_queue(self):
        """Assert that messages are deleted from SQS queue."""
        def create_mock_message(id, receipt_handle):
            mock_message = Mock()
            mock_message.Id = id
            mock_message.ReceiptHandle = receipt_handle
            return mock_message

        mock_queue_url = 'https://123.abc'
        mock_messages_to_delete = [
            create_mock_message(str(uuid.uuid4()), str(uuid.uuid4())),
            create_mock_message(str(uuid.uuid4()), str(uuid.uuid4()))
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
