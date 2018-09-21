"""Collection of tests for ``util.aws.sqs`` module."""
import json
import random
import uuid
from unittest.mock import Mock, patch

import faker
from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from util.aws import sqs
from util.tests import helper

_faker = faker.Faker()


class UtilAwsSqsTest(TestCase):
    """AWS SQS utility functions test case."""

    def test_receive_message_from_queue(self):
        """Assert that SQS Message objects are received."""
        mock_queue_url = 'https://123.abc'
        mock_message = Mock()

        with patch.object(sqs, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.receive_messages.return_value = [mock_message]

            actual_messages = sqs.receive_messages_from_queue(mock_queue_url)
            mock_resource.Queue.assert_called_with(mock_queue_url)

        self.assertEqual(mock_message, actual_messages[0])

    def test_yield_messages_from_queue(self):
        """Assert that yield_messages_from_queue yields messages."""
        queue_url = _faker.url()
        available_messages = [Mock(), Mock(), Mock()]

        with patch.object(sqs, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.receive_messages.side_effect = [
                [available_messages[0]],
                [available_messages[1]],
                [available_messages[2]],
            ]

            yielded_messages = []
            for message in sqs.yield_messages_from_queue(queue_url):
                yielded_messages.append(message)

            self.assertEqual(yielded_messages, available_messages)

    def test_yield_messages_from_queue_max_number_stop(self):
        """Assert that yield_messages_from_queue yields messages."""
        queue_url = _faker.url()
        available_messages = [Mock(), Mock(), Mock()]
        max_count = 2

        with patch.object(sqs, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.receive_messages.side_effect = [
                [available_messages[0]],
                [available_messages[1]],
                [available_messages[2]],
            ]

            yield_counter = 0
            yielded_messages = []
            for message in sqs.yield_messages_from_queue(queue_url, max_count):
                yield_counter += 1
                yielded_messages.append(message)

            self.assertEqual(yield_counter, max_count)
            self.assertEqual(yielded_messages, available_messages[:max_count])

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

        with patch.object(sqs, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.delete_messages.return_value = mock_response

            actual_response = sqs.delete_messages_from_queue(
                mock_queue_url,
                mock_messages_to_delete
            )

        self.assertEqual(mock_response, actual_response)

    def test_delete_message_from_queue_with_empty_list(self):
        """Assert an empty list of messages handled by delete."""
        mock_queue_url = 'https://123.abc'
        mock_messages_to_delete = []
        mock_response = {}

        actual_response = sqs.delete_messages_from_queue(
            mock_queue_url,
            mock_messages_to_delete
        )

        self.assertEqual(mock_response, actual_response)

    def test_get_sqs_queue_url_for_existing_queue(self):
        """Test getting URL for existing SQS queue."""
        queue_name = Mock()
        expected_url = Mock()
        mock_client = Mock()

        with patch.object(sqs, 'boto3') as mock_boto3:
            mock_boto3.client.return_value = mock_client
            mock_client.get_queue_url.return_value = {'QueueUrl': expected_url}
            queue_url = sqs.get_sqs_queue_url(queue_name)

        self.assertEqual(queue_url, expected_url)
        mock_client.get_queue_url.assert_called_with(QueueName=queue_name)

    def test_get_sqs_queue_url_creates_new_queue(self):
        """Test getting URL for a SQS queue that does not yet exist."""
        queue_name = Mock()
        expected_url = Mock()
        mock_client = Mock()

        error_response = {
            'Error': {
                'Code': '.NonExistentQueue'
            }
        }
        exception = ClientError(error_response, Mock())

        with patch.object(sqs, 'boto3') as mock_boto3, \
                patch.object(sqs, 'create_queue') as mock_create_queue:
            mock_boto3.client.return_value = mock_client
            mock_client.get_queue_url.side_effect = exception
            mock_create_queue.return_value = expected_url
            queue_url = sqs.get_sqs_queue_url(queue_name)
            mock_create_queue.assert_called_with(queue_name)

        self.assertEqual(queue_url, expected_url)
        mock_client.get_queue_url.assert_called_with(QueueName=queue_name)

    def test_create_queue_also_creates_dlq(self):
        """Test creating an SQS queue also creates a DLQ."""
        queue_name = _faker.slug()
        queue_url = Mock()

        mock_client = Mock()
        mock_client.create_queue.return_value = {'QueueUrl': queue_url}

        expected_queue_attributes = {
            'MessageRetentionPeriod': str(sqs.RETENTION_DEFAULT),
        }

        with patch.object(sqs, 'boto3') as mock_boto3, \
                patch.object(sqs, 'ensure_queue_has_dlq') as mock_ensure:
            mock_boto3.client.return_value = mock_client
            actual_queue_url = sqs.create_queue(queue_name)
            mock_ensure.assert_called_with(queue_name, queue_url)
            mock_client.set_queue_attributes.assert_called_with(
                QueueUrl=queue_url, Attributes=expected_queue_attributes
            )

        self.assertEqual(actual_queue_url, queue_url)

    def test_create_queue_without_dlq(self):
        """Test creating an SQS queue with retention period and no DLQ."""
        queue_name = _faker.slug()
        queue_url = Mock()
        retention = random.randint(1, sqs.RETENTION_MAXIMUM)

        mock_client = Mock()
        mock_client.create_queue.return_value = {'QueueUrl': queue_url}

        expected_queue_attributes = {
            'MessageRetentionPeriod': str(retention),
        }

        with patch.object(sqs, 'boto3') as mock_boto3, \
                patch.object(sqs, 'ensure_queue_has_dlq') as mock_ensure:
            mock_boto3.client.return_value = mock_client
            actual_queue_url = sqs.create_queue(queue_name, False, retention)
            mock_ensure.assert_not_called()
            mock_client.set_queue_attributes.assert_called_with(
                QueueUrl=queue_url, Attributes=expected_queue_attributes
            )

        self.assertEqual(actual_queue_url, queue_url)

    def test_create_dlq(self):
        """Test creation of DLQ for a source queue."""
        source_queue_name = _faker.slug()
        expected_dlq_name = '{}-dlq'.format(
            source_queue_name[:sqs.QUEUE_NAME_LENGTH_MAX - 4]
        )
        mock_client = Mock()
        mock_client.get_queue_attributes.return_value = {
            'Attributes': {
                'QueueArn': helper.generate_dummy_arn()
            }
        }
        with patch.object(sqs, 'boto3') as mock_boto3, \
                patch.object(sqs, 'create_queue') as mock_create:
            mock_boto3.client.return_value = mock_client
            sqs.create_dlq(source_queue_name)
            mock_create.assert_called_with(
                expected_dlq_name,
                with_dlq=False,
                retention_period=sqs.RETENTION_MAXIMUM
            )
            mock_client.get_queue_attributes.assert_called_with(
                QueueUrl=mock_create.return_value, AttributeNames=['QueueArn']
            )

    def test_ensure_queue_has_dlq(self):
        """Test that a queue without redrive policy gets a DLQ."""
        source_queue_name = _faker.slug()
        source_queue_url = _faker.url()
        mock_client = Mock()
        mock_client.get_queue_attributes.return_value = {}
        dlq_arn = helper.generate_dummy_arn()
        expected_attributes = {
            'RedrivePolicy': json.dumps({
                'deadLetterTargetArn': dlq_arn,
                'maxReceiveCount': settings.AWS_SQS_MAX_RECEIVE_COUNT,
            }),
        }
        with patch.object(sqs, 'boto3') as mock_boto3, \
                patch.object(sqs, 'create_dlq') as mock_create_dlq:
            mock_boto3.client.return_value = mock_client
            mock_create_dlq.return_value = dlq_arn
            sqs.ensure_queue_has_dlq(source_queue_name, source_queue_url)
            mock_create_dlq.assert_called_with(source_queue_name)
        mock_client.get_queue_attributes.assert_called_with(
            QueueUrl=source_queue_url,
            AttributeNames=['RedrivePolicy']
        )
        mock_client.set_queue_attributes.assert_called_with(
            QueueUrl=source_queue_url,
            Attributes=expected_attributes
        )

    def test_ensure_queue_has_dql_but_already_has_redrive(self):
        """Test that a queue with redrive policy does not get a DLQ."""
        source_queue_name = _faker.slug()
        source_queue_url = _faker.url()
        mock_client = Mock()
        mock_client.get_queue_attributes.return_value = {
            'Attributes': {
                'RedrivePolicy': '{"hello": "world"}',
            }
        }
        with patch.object(sqs, 'boto3') as mock_boto3, \
                patch.object(sqs, 'create_dlq') as mock_create_dlq:
            mock_boto3.client.return_value = mock_client
            sqs.ensure_queue_has_dlq(source_queue_name, source_queue_url)
            mock_create_dlq.assert_not_called()
        mock_client.get_queue_attributes.assert_called_with(
            QueueUrl=source_queue_url,
            AttributeNames=['RedrivePolicy']
        )
        mock_client.set_queue_attributes.assert_not_called()
