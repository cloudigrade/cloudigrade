"""Collection of tests for utils in the account app."""
import random
import uuid
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.test import TestCase
from rest_framework.serializers import ValidationError

import util.aws.sqs
from account import AWS_PROVIDER_STRING, util
from account.models import AwsAccount, AwsMachineImage
from account.util import convert_param_to_int
from util import aws
from util.tests import helper as util_helper


class AccountUtilTest(TestCase):
    """Account util test cases."""

    def test_create_new_machine_images(self):
        """Test that new machine images are saved to the DB."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        account = AwsAccount(
            account_arn=arn,
            aws_account_id=aws_account_id,
            user=util_helper.generate_test_user(),
        )
        account.save()

        region = random.choice(util_helper.SOME_AWS_REGIONS)
        instances_data = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        ami_id = instances_data[region][0]['ImageId']

        mock_session = Mock()
        described_amis = util_helper.generate_dummy_describe_image(
            image_id=ami_id,
            owner_id=aws_account_id
        )

        with patch.object(util.aws, 'describe_images') as mock_describe_images:
            mock_describe_images.return_value = [described_amis]
            result = util.create_new_machine_images(mock_session,
                                                    instances_data)
            mock_describe_images.assert_called_with(mock_session, {ami_id},
                                                    region)

        self.assertEqual(result, [ami_id])

        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].ec2_ami_id, ami_id)

    def test_create_new_machine_images_with_windows_image(self):
        """Test that new windows machine images are marked appropriately."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        account = AwsAccount(
            account_arn=arn,
            aws_account_id=aws_account_id,
            user=util_helper.generate_test_user(),
        )
        account.save()

        region = random.choice(util_helper.SOME_AWS_REGIONS)
        instances_data = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        instances_data[region][0]['Platform'] = 'Windows'
        ami_id = instances_data[region][0]['ImageId']

        mock_session = Mock()
        described_amis = util_helper.generate_dummy_describe_image(
            image_id=ami_id,
            owner_id=aws_account_id,
        )

        with patch.object(util.aws, 'describe_images') as mock_describe_images:
            mock_describe_images.return_value = [described_amis]
            result = util.create_new_machine_images(mock_session,
                                                    instances_data)
            mock_describe_images.assert_called_with(mock_session, {ami_id},
                                                    region)

        self.assertEqual(result, [ami_id])

        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].ec2_ami_id, ami_id)
        self.assertEqual(images[0].platform, AwsMachineImage.WINDOWS)

    def test_generate_aws_ami_messages(self):
        """Test that messages are formatted correctly."""
        region = random.choice(util_helper.SOME_AWS_REGIONS)
        instance = util_helper.generate_dummy_describe_instance()
        instances_data = {region: [instance]}
        ami_list = [instance['ImageId']]

        expected = [{'cloud_provider': AWS_PROVIDER_STRING,
                     'region': region,
                     'image_id': instance['ImageId']}]

        result = util.generate_aws_ami_messages(instances_data, ami_list)

        self.assertEqual(result, expected)

    def test_sqs_wrap_message(self):
        """Test SQS message wrapping."""
        message_decoded = {'hello': 'world'}
        message_encoded = '{"hello": "world"}'
        with patch.object(util, 'uuid') as mock_uuid:
            wrapped_id = uuid.uuid4()
            mock_uuid.uuid4.return_value = wrapped_id
            actual_wrapped = util._sqs_wrap_message(message_decoded)
        self.assertEqual(actual_wrapped['Id'], str(wrapped_id))
        self.assertEqual(actual_wrapped['MessageBody'], message_encoded)

    def test_sqs_unwrap_message(self):
        """Test SQS message unwrapping."""
        message_decoded = {'hello': 'world'}
        message_encoded = '{"hello": "world"}'
        message_wrapped = {
            'Body': message_encoded,
        }
        actual_unwrapped = util._sqs_unwrap_message(message_wrapped)
        self.assertEqual(actual_unwrapped, message_decoded)

    def create_messages(self, count=1):
        """
        Create lists of messages for testing.

        Args:
            count (int): number of messages to generate

        Returns:
            tuple: Three lists. The first list contains the original message
                payloads. The second list contains the messages wrapped as we
                would batch send to SQS. The third list contains the messages
                wrapped as we would received from SQS.

        """
        payloads = []
        messages_sent = []
        messages_received = []
        for __ in range(count):
            message = f'Hello, {uuid.uuid4()}!'
            wrapped = util._sqs_wrap_message(message)
            payloads.append(message)
            messages_sent.append(wrapped)
            received = {
                'Id': wrapped['Id'],
                'Body': wrapped['MessageBody'],
                'ReceiptHandle': uuid.uuid4(),
            }
            messages_received.append(received)
        return payloads, messages_sent, messages_received

    @patch('account.util.boto3')
    @patch('account.util.aws.sqs.boto3')
    def test_add_messages_to_queue(self, mock_sqs_boto3, mock_boto3):
        """Test that messages get added to a message queue."""
        queue_name = 'Test Queue'
        messages, wrapped_messages, __ = self.create_messages()
        mock_sqs = mock_boto3.client.return_value
        mock_queue_url = Mock()
        mock_sqs_boto3.client.return_value.get_queue_url.return_value = {
            'QueueUrl': mock_queue_url
        }

        with patch.object(util, '_sqs_wrap_message') as mock_sqs_wrap_message:
            mock_sqs_wrap_message.return_value = wrapped_messages[0]
            util.add_messages_to_queue(queue_name, messages)
            mock_sqs_wrap_message.assert_called_once_with(messages[0])

        mock_sqs.send_message_batch.assert_called_with(
            QueueUrl=mock_queue_url, Entries=wrapped_messages
        )

    @patch('account.util.boto3')
    @patch('account.util.aws.sqs.boto3')
    def test_read_single_message_from_queue(self, mock_sqs_boto3, mock_boto3):
        """Test that messages are read from a message queue."""
        queue_name = 'Test Queue'
        actual_count = util.SQS_RECEIVE_BATCH_SIZE + 1
        requested_count = 1

        messages, __, wrapped_messages = self.create_messages(actual_count)
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[:requested_count]},
            {'Messages': []},
        ]
        read_messages = util.read_messages_from_queue(queue_name,
                                                      requested_count)
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch('account.util.boto3')
    @patch('account.util.aws.sqs.boto3')
    def test_read_messages_from_queue_until_empty(self, mock_sqs_boto3,
                                                  mock_boto3):
        """Test that all messages are read from a message queue."""
        queue_name = 'Test Queue'
        requested_count = util.SQS_RECEIVE_BATCH_SIZE + 1
        actual_count = util.SQS_RECEIVE_BATCH_SIZE - 1

        messages, __, wrapped_messages = self.create_messages(actual_count)
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[:util.SQS_RECEIVE_BATCH_SIZE]},
            {'Messages': []},
        ]
        read_messages = util.read_messages_from_queue(queue_name,
                                                      requested_count)
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch('account.util.boto3')
    @patch('account.util.aws.sqs.boto3')
    def test_read_messages_from_queue_stops_at_limit(self, mock_sqs_boto3,
                                                     mock_boto3):
        """Test that all messages are read from a message queue."""
        queue_name = 'Test Queue'
        requested_count = util.SQS_RECEIVE_BATCH_SIZE - 1
        actual_count = util.SQS_RECEIVE_BATCH_SIZE + 1

        messages, __, wrapped_messages = self.create_messages(actual_count)
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[:requested_count]},
            {'Messages': []},
        ]
        read_messages = util.read_messages_from_queue(queue_name,
                                                      requested_count)
        self.assertEqual(set(read_messages), set(messages[:requested_count]))

    @patch('account.util.boto3')
    @patch('account.util.aws.sqs.boto3')
    def test_read_messages_from_queue_stops_has_error(self, mock_sqs_boto3,
                                                      mock_boto3):
        """Test we log if an error is raised when deleting from a queue."""
        queue_name = 'Test Queue'
        requested_count = util.SQS_RECEIVE_BATCH_SIZE - 1
        actual_count = util.SQS_RECEIVE_BATCH_SIZE + 1

        messages, __, wrapped_messages = self.create_messages(actual_count)
        mock_sqs = mock_boto3.client.return_value
        mock_sqs.receive_message = Mock()
        mock_sqs.receive_message.side_effect = [
            {'Messages': wrapped_messages[:requested_count]},
            {'Messages': []},
        ]
        error_response = {
            'Error': {
                'Code': 'it is a mystery'
            }
        }
        exception = ClientError(error_response, Mock())
        mock_sqs.delete_message.side_effect = exception
        read_messages = util.read_messages_from_queue(queue_name,
                                                      requested_count)
        self.assertEqual(set(read_messages), set())

    def test_convert_param_to_int_with_int(self):
        """Test that convert_param_to_int returns int with int."""
        result = convert_param_to_int('test_field', 42)
        self.assertEqual(result, 42)

    def test_convert_param_to_int_with_str_int(self):
        """Test that convert_param_to_int returns int with str int."""
        result = convert_param_to_int('test_field', '42')
        self.assertEqual(result, 42)

    def test_convert_param_to_int_with_str(self):
        """Test that convert_param_to_int returns int with str."""
        with self.assertRaises(ValidationError):
            convert_param_to_int('test_field', 'not_int')
