"""Collection of tests for ``util.aws.sqs`` module."""
import json
import random
import uuid
from unittest.mock import Mock, patch

import faker
from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from api.tests import helper as api_helper
from util.aws import sqs
from util.aws.sqs import SQS_RECEIVE_BATCH_SIZE, read_messages_from_queue
from util.tests import helper

_faker = faker.Faker()


class UnexpectedException(Exception):
    """Dummy exception for testing."""


class UtilAwsSqsTest(TestCase):
    """AWS SQS utility functions test case."""

    def test_receive_message_from_queue(self):
        """Assert that SQS Message objects are received."""
        mock_queue_url = "https://123.abc"
        mock_message = Mock()

        with patch.object(sqs, "boto3") as mock_boto3:
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

        with patch.object(sqs, "boto3") as mock_boto3:
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

    def test_yield_messages_from_queue_no_messages(self):
        """Assert that yield_messages_from_queue breaks when no messages."""
        queue_url = _faker.url()

        with patch.object(sqs, "boto3") as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.receive_messages.side_effect = [None]

            yielded_messages = []
            for message in sqs.yield_messages_from_queue(queue_url):
                yielded_messages.append(message)

            self.assertEqual(yielded_messages, [])

    def test_yield_messages_from_queue_max_number_stop(self):
        """Assert that yield_messages_from_queue yields messages."""
        queue_url = _faker.url()
        available_messages = [Mock(), Mock(), Mock()]
        max_count = 2

        with patch.object(sqs, "boto3") as mock_boto3:
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

    def test_yield_messages_from_queue_not_exists(self):
        """Assert yield_messages_from_queue handles a nonexistent queue."""
        queue_url = _faker.url()
        error_response = {"Error": {"Code": ".NonExistentQueue"}}
        exception = ClientError(error_response, Mock())

        with self.assertLogs(
            "util.aws.sqs", level="WARNING"
        ) as logging_watcher, patch.object(sqs, "boto3") as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.receive_messages.side_effect = exception
            yielded_messages = list(sqs.yield_messages_from_queue(queue_url))

        self.assertEqual(len(yielded_messages), 0)
        self.assertIn("Queue does not yet exist at", logging_watcher.output[0])

    def test_yield_messages_from_queue_other_client_error(self):
        """Assert yield_messages_from_queue logs and raises other ClientError."""
        queue_url = _faker.url()
        error_response = {"Error": {"Code": ".Potatoes"}}
        exception = ClientError(error_response, Mock())

        with self.assertLogs(
            "util.aws.sqs", level="ERROR"
        ) as logging_watcher, patch.object(sqs, "boto3") as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.receive_messages.side_effect = exception
            with self.assertRaises(ClientError) as raised_exception:
                list(sqs.yield_messages_from_queue(queue_url))

        self.assertEqual(raised_exception.exception, exception)
        self.assertIn(
            "Unexpected ClientError when receiving message from SQS",
            logging_watcher.output[0],
        )

    def test_yield_messages_from_queue_raises_unhandled_exception(self):
        """Assert yield_messages_from_queue logs and raises other exceptions."""
        queue_url = _faker.url()
        exception = UnexpectedException()

        with self.assertLogs(
            "util.aws.sqs", level="ERROR"
        ) as logging_watcher, patch.object(sqs, "boto3") as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.receive_messages.side_effect = exception
            with self.assertRaises(UnexpectedException) as raised_exception:
                list(sqs.yield_messages_from_queue(queue_url))

        self.assertEqual(raised_exception.exception, exception)
        self.assertIn(
            "Unexpected not-ClientError exception when receiving message from SQS",
            logging_watcher.output[0],
        )

    def test_delete_message_from_queue(self):
        """Assert that messages are deleted from SQS queue."""
        mock_queue_url = "https://123.abc"
        message_data = [
            [str(uuid.uuid4()), "message 1", str(uuid.uuid4())],
            [str(uuid.uuid4()), "message 2", str(uuid.uuid4())],
        ]
        mock_messages_to_delete = [
            helper.generate_mock_sqs_message(*message_data[0]),
            helper.generate_mock_sqs_message(*message_data[1]),
        ]
        expected_delete_entries = [
            {"Id": message_data[0][0], "ReceiptHandle": message_data[0][2]},
            {"Id": message_data[1][0], "ReceiptHandle": message_data[1][2]},
        ]
        mock_response = {
            "ResponseMetadata": {
                "HTTPHeaders": {
                    "connection": "keep-alive",
                    "content-length": "1358",
                    "content-type": "text/xml",
                    "date": "Mon, 19 Feb 2018 20:31:09 GMT",
                    "server": "Server",
                    "x-amzn-requestid": "1234",
                },
                "HTTPStatusCode": 200,
                "RequestId": "123456",
                "RetryAttempts": 0,
            },
            "Successful": [
                {"Id": "fe3b9df2-416c-4ee2-a04e-7ba8b80490ca"},
                {"Id": "3dc419e6-b841-48ad-ae4d-57da10a4315a"},
            ],
        }

        with patch.object(sqs, "boto3") as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_queue = mock_resource.Queue.return_value
            mock_queue.delete_messages.return_value = mock_response

            actual_response = sqs.delete_messages_from_queue(
                mock_queue_url, mock_messages_to_delete
            )

        self.assertEqual(mock_response, actual_response)
        mock_queue.delete_messages.assert_called_with(Entries=expected_delete_entries)

    def test_delete_message_from_queue_with_empty_list(self):
        """Assert an empty list of messages handled by delete."""
        mock_queue_url = "https://123.abc"
        mock_messages_to_delete = []
        mock_response = {}

        actual_response = sqs.delete_messages_from_queue(
            mock_queue_url, mock_messages_to_delete
        )

        self.assertEqual(mock_response, actual_response)

    def test_get_sqs_queue_url_for_existing_queue(self):
        """Test getting URL for existing SQS queue."""
        queue_name = _faker.slug()
        expected_url = _faker.url()
        mock_client = Mock()

        with patch.object(sqs, "boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_client
            mock_client.get_queue_url.return_value = {"QueueUrl": expected_url}
            queue_url = sqs.get_sqs_queue_url(queue_name)

        self.assertEqual(queue_url, expected_url)
        mock_client.get_queue_url.assert_called_with(QueueName=queue_name)

    def test_get_sqs_queue_url_creates_new_queue(self):
        """Test getting URL for a SQS queue that does not yet exist."""
        queue_name = _faker.slug()
        expected_url = _faker.url()
        mock_client = Mock()

        error_response = {"Error": {"Code": ".NonExistentQueue"}}
        exception = ClientError(error_response, Mock())

        with patch.object(sqs, "boto3") as mock_boto3, patch.object(
            sqs, "create_queue"
        ) as mock_create_queue:
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
        mock_client.create_queue.return_value = {"QueueUrl": queue_url}

        expected_queue_attributes = {
            "MessageRetentionPeriod": str(sqs.RETENTION_DEFAULT),
        }

        with patch.object(sqs, "boto3") as mock_boto3, patch.object(
            sqs, "ensure_queue_has_dlq"
        ) as mock_ensure:
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
        queue_url = _faker.url()
        retention = random.randint(1, sqs.RETENTION_MAXIMUM)

        mock_client = Mock()
        mock_client.create_queue.return_value = {"QueueUrl": queue_url}

        expected_queue_attributes = {
            "MessageRetentionPeriod": str(retention),
        }

        with patch.object(sqs, "boto3") as mock_boto3, patch.object(
            sqs, "ensure_queue_has_dlq"
        ) as mock_ensure:
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
        expected_dlq_name = "{}-dlq".format(
            source_queue_name[: sqs.QUEUE_NAME_LENGTH_MAX - 4]
        )
        mock_client = Mock()
        mock_client.get_queue_attributes.return_value = {
            "Attributes": {"QueueArn": helper.generate_dummy_arn()}
        }
        with patch.object(sqs, "boto3") as mock_boto3, patch.object(
            sqs, "create_queue"
        ) as mock_create:
            mock_boto3.client.return_value = mock_client
            sqs.create_dlq(source_queue_name)
            mock_create.assert_called_with(
                expected_dlq_name,
                with_dlq=False,
                retention_period=sqs.RETENTION_MAXIMUM,
            )
            mock_client.get_queue_attributes.assert_called_with(
                QueueUrl=mock_create.return_value, AttributeNames=["QueueArn"]
            )

    def test_ensure_queue_has_dlq(self):
        """Test that a queue without redrive policy gets a DLQ."""
        source_queue_name = _faker.slug()
        source_queue_url = _faker.url()
        mock_client = Mock()
        mock_client.get_queue_attributes.return_value = {}
        dlq_arn = helper.generate_dummy_arn()
        expected_attributes = {
            "RedrivePolicy": json.dumps(
                {
                    "deadLetterTargetArn": dlq_arn,
                    "maxReceiveCount": settings.AWS_SQS_MAX_RECEIVE_COUNT,
                }
            ),
        }
        with patch.object(sqs, "boto3") as mock_boto3, patch.object(
            sqs, "create_dlq"
        ) as mock_create_dlq, patch.object(
            sqs, "validate_redrive_policy"
        ) as mock_validate:
            mock_boto3.client.return_value = mock_client
            mock_validate.return_value = False
            mock_create_dlq.return_value = dlq_arn
            sqs.ensure_queue_has_dlq(source_queue_name, source_queue_url)
            mock_create_dlq.assert_called_with(source_queue_name)
        mock_client.get_queue_attributes.assert_called_with(
            QueueUrl=source_queue_url, AttributeNames=["RedrivePolicy"]
        )
        mock_validate.assert_called_with(source_queue_name, {})
        mock_client.set_queue_attributes.assert_called_with(
            QueueUrl=source_queue_url, Attributes=expected_attributes
        )

    def test_ensure_queue_has_dlq_but_already_has_redrive(self):
        """Test that a queue with redrive policy does not get a DLQ."""
        source_queue_name = _faker.slug()
        source_queue_url = _faker.url()
        mock_client = Mock()
        mock_client.get_queue_attributes.return_value = {
            "Attributes": {
                "RedrivePolicy": '{"hello": "world"}',
            }
        }
        with patch.object(sqs, "boto3") as mock_boto3, patch.object(
            sqs, "create_dlq"
        ) as mock_create_dlq, patch.object(
            sqs, "validate_redrive_policy"
        ) as mock_validate:
            mock_boto3.client.return_value = mock_client
            mock_validate.return_value = True
            sqs.ensure_queue_has_dlq(source_queue_name, source_queue_url)
            mock_create_dlq.assert_not_called()
        mock_validate.assert_called_with(source_queue_name, {"hello": "world"})
        mock_client.get_queue_attributes.assert_called_with(
            QueueUrl=source_queue_url, AttributeNames=["RedrivePolicy"]
        )
        mock_client.set_queue_attributes.assert_not_called()

    def test_validate_redrive_policy_no_arn_invalid(self):
        """Test redrive policy is not valid if no queue ARN."""
        source_queue_name = _faker.slug()
        redrive_policy = {}
        self.assertFalse(sqs.validate_redrive_policy(source_queue_name, redrive_policy))

    def test_validate_redrive_policy_malformed_arn_invalid(self):
        """Test redrive policy is not valid if queue ARN is malformed."""
        source_queue_name = _faker.slug()
        redrive_policy = {"deadLetterTargetArn": _faker.slug()}
        self.assertFalse(sqs.validate_redrive_policy(source_queue_name, redrive_policy))

    def test_validate_redrive_policy_queue_not_exists_invalid(self):
        """Test redrive policy is not valid if target queue does not exist."""
        source_queue_name = _faker.slug()
        dlq_name = _faker.slug()
        dlq_arn = helper.generate_dummy_arn(resource=dlq_name)
        redrive_policy = {
            "deadLetterTargetArn": dlq_arn,
        }
        mock_client = Mock()
        mock_client.get_queue_url.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "Random.Something.NonExistentQueue",
                }
            },
            operation_name=Mock(),
        )
        with patch.object(sqs, "boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_client
            self.assertFalse(
                sqs.validate_redrive_policy(source_queue_name, redrive_policy)
            )
        mock_client.get_queue_url.assert_called_with(QueueName=dlq_name)

    def test_validate_redrive_policy_queue_exists_valid(self):
        """Test redrive policy is valid if target queue exists."""
        source_queue_name = _faker.slug()
        dlq_name = _faker.slug()
        dlq_arn = helper.generate_dummy_arn(resource=dlq_name)
        dlq_url = _faker.url()
        redrive_policy = {
            "deadLetterTargetArn": dlq_arn,
        }
        mock_client = Mock()
        mock_client.get_queue_url.return_value = {"QueueUrl": dlq_url}
        with patch.object(sqs, "boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_client
            self.assertTrue(
                sqs.validate_redrive_policy(source_queue_name, redrive_policy)
            )
        mock_client.get_queue_url.assert_called_with(QueueName=dlq_name)

    def test_get_sqs_approximate_number_of_messages(self):
        """Test get_sqs_approximate_number_of_messages with valid queue and response."""
        queue_url = _faker.url()
        expected_number = _faker.random_int()
        mock_client = Mock()
        mock_client.get_queue_attributes.return_value = {
            "Attributes": {"ApproximateNumberOfMessages": str(expected_number)}
        }
        with patch.object(sqs, "boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_client
            actual_number = sqs.get_sqs_approximate_number_of_messages(queue_url)

        self.assertEqual(expected_number, actual_number)
        mock_client.get_queue_attributes.assert_called_with(
            QueueUrl=queue_url, AttributeNames=["ApproximateNumberOfMessages"]
        )

    def test_get_sqs_approximate_number_of_messages_queue_does_not_exist(self):
        """
        Test get_sqs_approximate_number_of_messages with queue that doesn't exist.

        We expect the AWS error to be logged and return None.
        """
        queue_url = _faker.url()
        mock_client = Mock()
        error_response = {"Error": {"Code": f"{_faker.slug()}.NonExistentQueue"}}
        exception = ClientError(error_response, Mock())
        mock_client.get_queue_attributes.side_effect = exception

        with self.assertLogs(
            "util.aws.sqs", level="WARNING"
        ) as logging_watcher, patch.object(sqs, "boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_client
            actual_number = sqs.get_sqs_approximate_number_of_messages(queue_url)

        self.assertEqual(None, actual_number)
        self.assertIn("Queue does not exist at", logging_watcher.output[0])
        mock_client.get_queue_attributes.assert_called_with(
            QueueUrl=queue_url, AttributeNames=["ApproximateNumberOfMessages"]
        )

    def test_get_sqs_approximate_number_of_messages_unexpected_aws_error(self):
        """
        Test get_sqs_approximate_number_of_messages with unexpected AWS error.

        We expect the AWS error to be logged and return None.
        """
        queue_url = _faker.url()
        mock_client = Mock()
        error_response = {"Error": {"Code": f"{_faker.slug()}.{_faker.slug()}"}}
        exception = ClientError(error_response, Mock())
        mock_client.get_queue_attributes.side_effect = exception

        with self.assertLogs(
            "util.aws.sqs", level="ERROR"
        ) as logging_watcher, patch.object(sqs, "boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_client
            actual_number = sqs.get_sqs_approximate_number_of_messages(queue_url)

        self.assertEqual(None, actual_number)
        self.assertIn("Unexpected ClientError", logging_watcher.output[0])
        mock_client.get_queue_attributes.assert_called_with(
            QueueUrl=queue_url, AttributeNames=["ApproximateNumberOfMessages"]
        )

    def test_get_sqs_approximate_number_of_messages_unexpected_exception(self):
        """
        Test get_sqs_approximate_number_of_messages with unexpected exception.

        We expect the exception to be logged and return None.
        """
        queue_url = _faker.url()
        mock_client = Mock()
        exception = UnexpectedException()
        mock_client.get_queue_attributes.side_effect = exception

        with self.assertLogs(
            "util.aws.sqs", level="ERROR"
        ) as logging_watcher, patch.object(sqs, "boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_client
            actual_number = sqs.get_sqs_approximate_number_of_messages(queue_url)

        self.assertEqual(None, actual_number)
        self.assertIn("Unexpected not-ClientError exception", logging_watcher.output[0])
        mock_client.get_queue_attributes.assert_called_with(
            QueueUrl=queue_url, AttributeNames=["ApproximateNumberOfMessages"]
        )

    def test_set_visibility_timeout(self):
        """Test setting an SQS queue's visibility timeout attribute."""
        queue_name = _faker.slug()
        timeout = _faker.random_int()

        expected_queue_attributes = {"VisibilityTimeout": str(timeout)}

        with patch.object(sqs, "boto3") as mock_boto3, patch.object(
            sqs, "get_sqs_queue_url"
        ) as mock_get_sqs_queue_url:
            mock_client = mock_boto3.client.return_value
            queue_url = mock_get_sqs_queue_url.return_value

            sqs.set_visibility_timeout(queue_name, timeout)

            mock_get_sqs_queue_url.assert_called_with(queue_name)
            mock_client.set_queue_attributes.assert_called_with(
                QueueUrl=queue_url, Attributes=expected_queue_attributes
            )


class ReadMessagesFromQueueTest(TestCase):
    """Test cases for util.aws.read_messages_from_queue."""

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
        mock_sqs.get_queue_url.return_value = {"QueueUrl": _faker.url()}
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
        mock_sqs.get_queue_url.return_value = {"QueueUrl": _faker.url()}
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
        mock_sqs.get_queue_url.return_value = {"QueueUrl": _faker.url()}
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
        mock_sqs.get_queue_url.return_value = {"QueueUrl": _faker.url()}
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


class ExtractSqsMessageTest(TestCase):
    """Test cases for util.aws.sqs.extract_sqs_message."""

    def test_extract_sqs_message(self):
        """Test extract_sqs_message happy path."""
        record = _faker.slug()
        body = {"Records": [{"s3": record}]}
        message_body = json.dumps(body)
        sqs_message = helper.generate_mock_sqs_message(
            _faker.uuid4(), message_body, _faker.uuid4()
        )
        expected_result = [record]
        actual_result = sqs.extract_sqs_message(sqs_message)
        self.assertEqual(expected_result, actual_result)

    def test_extract_sqs_message_no_body(self):
        """Test extract_sqs_message failure when message has no body."""
        broken_message = object()
        with self.assertRaises(AttributeError) as error_cm, self.assertLogs(
            "util.aws.sqs", level="ERROR"
        ) as log_context:
            sqs.extract_sqs_message(broken_message)
        self.assertEqual(
            f"Unexpected failure ({error_cm.exception.args[0]}) loading SQS "
            f"message.body: {None}",
            log_context.records[0].message,
        )

    def test_extract_sqs_message_not_json(self):
        """Test extract_sqs_message failure when message body cannot parse to JSON."""
        not_json_string = _faker.sentence()
        broken_message = helper.generate_mock_sqs_message(
            _faker.uuid4(), not_json_string, _faker.uuid4()
        )
        with self.assertRaises(json.JSONDecodeError) as error_cm, self.assertLogs(
            "util.aws.sqs", level="ERROR"
        ) as log_context:
            sqs.extract_sqs_message(broken_message)
        self.assertEqual(
            f"Unexpected failure ({error_cm.exception.args[0]}) loading SQS "
            f"message.body: {not_json_string}",
            log_context.records[0].message,
        )
