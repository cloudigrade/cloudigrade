"""Collection of tests for the api.clouds.aws.util module."""
import uuid
from unittest.mock import Mock, patch

from django.test import TestCase

from api import AWS_PROVIDER_STRING
from api.clouds.aws import util
from api.clouds.aws.util import generate_aws_ami_messages
from api.tests import helper as api_helper
from util.aws.sqs import _sqs_unwrap_message, _sqs_wrap_message, add_messages_to_queue
from util.tests import helper as util_helper


class CloudsAwsUtilTest(TestCase):
    """Miscellaneous test cases for api.clouds.aws.util module functions."""

    def test_generate_aws_ami_messages(self):
        """Test that messages are formatted correctly."""
        region = util_helper.get_random_region()
        instance = util_helper.generate_dummy_describe_instance()
        instances_data = {region: [instance]}
        ami_list = [instance["ImageId"]]

        expected = [
            {
                "cloud_provider": AWS_PROVIDER_STRING,
                "region": region,
                "image_id": instance["ImageId"],
            }
        ]

        result = generate_aws_ami_messages(instances_data, ami_list)

        self.assertEqual(result, expected)

    def test_sqs_wrap_message(self):
        """Test SQS message wrapping."""
        message_decoded = {"hello": "world"}
        message_encoded = '{"hello": "world"}'
        with patch.object(util.aws.sqs, "uuid") as mock_uuid:
            wrapped_id = uuid.uuid4()
            mock_uuid.uuid4.return_value = wrapped_id
            actual_wrapped = _sqs_wrap_message(message_decoded)
        self.assertEqual(actual_wrapped["Id"], str(wrapped_id))
        self.assertEqual(actual_wrapped["MessageBody"], message_encoded)

    def test_sqs_unwrap_message(self):
        """Test SQS message unwrapping."""
        message_decoded = {"hello": "world"}
        message_encoded = '{"hello": "world"}'
        message_wrapped = {"Body": message_encoded}
        actual_unwrapped = _sqs_unwrap_message(message_wrapped)
        self.assertEqual(actual_unwrapped, message_decoded)

    @patch("api.clouds.aws.util.aws.sqs.boto3")
    def test_add_messages_to_queue(self, mock_boto3):
        """Test that messages get added to a message queue."""
        queue_name = "Test Queue"
        messages, wrapped_messages, __ = api_helper.create_messages_for_sqs()
        mock_sqs = mock_boto3.client.return_value
        mock_queue_url = Mock()
        mock_boto3.client.return_value.get_queue_url.return_value = {
            "QueueUrl": mock_queue_url
        }

        with patch.object(util.aws.sqs, "_sqs_wrap_message") as mock_sqs_wrap_message:
            mock_sqs_wrap_message.return_value = wrapped_messages[0]
            add_messages_to_queue(queue_name, messages)
            mock_sqs_wrap_message.assert_called_once_with(messages[0])

        mock_sqs.send_message_batch.assert_called_with(
            QueueUrl=mock_queue_url, Entries=wrapped_messages
        )
