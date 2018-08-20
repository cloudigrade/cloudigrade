"""Collection of tests for ``util.aws.sqs`` module."""
import uuid
from unittest.mock import Mock, patch

import faker
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
