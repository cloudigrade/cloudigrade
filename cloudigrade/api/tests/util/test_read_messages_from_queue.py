"""Collection of tests for api.util.read_messages_from_queue."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.test import TestCase

from api.tests import helper as api_helper
from util.aws.sqs import SQS_RECEIVE_BATCH_SIZE, read_messages_from_queue


class ReadMessagesFromQueueTest(TestCase):
    """Test cases for api.util.read_messages_from_queue."""

    @patch("util.aws.sqs.boto3")
    def test_read_single_message_from_queue(self, mock_boto3):
        """Test that messages are read from a message queue."""
        queue_name = "Test Queue"
        actual_count = SQS_RECEIVE_BATCH_SIZE + 1
        requested_count = 1

        messages, __, wrapped_messages = api_helper.create_messages_for_sqs(
            actual_count
        )
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {"Messages": wrapped_messages[:requested_count]},
            {"Messages": []},
        ]
        read_messages = read_messages_from_queue(queue_name, requested_count)
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch("util.aws.sqs.boto3")
    def test_read_messages_from_queue_until_empty(self, mock_boto3):
        """Test that all messages are read from a message queue."""
        queue_name = "Test Queue"
        requested_count = SQS_RECEIVE_BATCH_SIZE + 1
        actual_count = SQS_RECEIVE_BATCH_SIZE - 1

        messages, __, wrapped_messages = api_helper.create_messages_for_sqs(
            actual_count
        )
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {"Messages": wrapped_messages[:SQS_RECEIVE_BATCH_SIZE]},
            {"Messages": []},
        ]
        read_messages = read_messages_from_queue(queue_name, requested_count)
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch("util.aws.sqs.boto3")
    def test_read_messages_from_queue_stops_at_limit(self, mock_boto3):
        """Test that all messages are read from a message queue."""
        queue_name = "Test Queue"
        requested_count = SQS_RECEIVE_BATCH_SIZE - 1
        actual_count = SQS_RECEIVE_BATCH_SIZE + 1

        messages, __, wrapped_messages = api_helper.create_messages_for_sqs(
            actual_count
        )
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {"Messages": wrapped_messages[:requested_count]},
            {"Messages": []},
        ]
        read_messages = read_messages_from_queue(queue_name, requested_count)
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch("util.aws.sqs.boto3")
    def test_read_messages_from_queue_stops_has_error(self, mock_boto3):
        """Test we log if an error is raised when deleting from a queue."""
        queue_name = "Test Queue"
        requested_count = SQS_RECEIVE_BATCH_SIZE - 1
        actual_count = SQS_RECEIVE_BATCH_SIZE + 1

        messages, __, wrapped_messages = api_helper.create_messages_for_sqs(
            actual_count
        )
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {"Messages": wrapped_messages[:requested_count]},
            {"Messages": []},
        ]
        error_response = {"Error": {"Code": "it is a mystery"}}
        exception = ClientError(error_response, Mock())
        mock_sqs.delete_message.side_effect = exception
        read_messages = read_messages_from_queue(queue_name, requested_count)
        self.assertEqual(set(read_messages), set())
