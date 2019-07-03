"""Collection of tests for api.util.read_messages_from_queue."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.test import TestCase

import util.aws.sqs
from api import util
from api.tests import helper as api_helper


class ReadMessagesFromQueueTest(TestCase):
    """Test cases for api.util.read_messages_from_queue."""

    @patch('api.util.boto3')
    @patch('api.util.aws.sqs.boto3')
    def test_read_single_message_from_queue(self, mock_sqs_boto3, mock_boto3):
        """Test that messages are read from a message queue."""
        queue_name = 'Test Queue'
        actual_count = util.SQS_RECEIVE_BATCH_SIZE + 1
        requested_count = 1

        messages, __, wrapped_messages = api_helper.create_messages_for_sqs(
            actual_count
        )
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[:requested_count]},
            {'Messages': []},
        ]
        read_messages = util.read_messages_from_queue(
            queue_name, requested_count
        )
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch('api.util.boto3')
    @patch('api.util.aws.sqs.boto3')
    def test_read_messages_from_queue_until_empty(
        self, mock_sqs_boto3, mock_boto3
    ):
        """Test that all messages are read from a message queue."""
        queue_name = 'Test Queue'
        requested_count = util.SQS_RECEIVE_BATCH_SIZE + 1
        actual_count = util.SQS_RECEIVE_BATCH_SIZE - 1

        messages, __, wrapped_messages = api_helper.create_messages_for_sqs(
            actual_count
        )
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[: util.SQS_RECEIVE_BATCH_SIZE]},
            {'Messages': []},
        ]
        read_messages = util.read_messages_from_queue(
            queue_name, requested_count
        )
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch('api.util.boto3')
    @patch('api.util.aws.sqs.boto3')
    def test_read_messages_from_queue_stops_at_limit(
        self, mock_sqs_boto3, mock_boto3
    ):
        """Test that all messages are read from a message queue."""
        queue_name = 'Test Queue'
        requested_count = util.SQS_RECEIVE_BATCH_SIZE - 1
        actual_count = util.SQS_RECEIVE_BATCH_SIZE + 1

        messages, __, wrapped_messages = api_helper.create_messages_for_sqs(
            actual_count
        )
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[:requested_count]},
            {'Messages': []},
        ]
        read_messages = util.read_messages_from_queue(
            queue_name, requested_count
        )
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch('api.util.boto3')
    @patch('api.util.aws.sqs.boto3')
    def test_read_messages_from_queue_stops_has_error(
        self, mock_sqs_boto3, mock_boto3
    ):
        """Test we log if an error is raised when deleting from a queue."""
        queue_name = 'Test Queue'
        requested_count = util.SQS_RECEIVE_BATCH_SIZE - 1
        actual_count = util.SQS_RECEIVE_BATCH_SIZE + 1

        messages, __, wrapped_messages = api_helper.create_messages_for_sqs(
            actual_count
        )
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[:requested_count]},
            {'Messages': []},
        ]
        error_response = {'Error': {'Code': 'it is a mystery'}}
        exception = ClientError(error_response, Mock())
        mock_sqs.delete_message.side_effect = exception
        read_messages = util.read_messages_from_queue(
            queue_name, requested_count
        )
        self.assertEqual(set(read_messages), set())
