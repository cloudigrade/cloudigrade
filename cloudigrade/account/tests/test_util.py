"""Collection of tests for utils in the account app."""
import random
from queue import Empty
from unittest.mock import Mock, patch

from django.test import TestCase

from account import AWS_PROVIDER_STRING, util
from account.models import AwsAccount, AwsMachineImage
from util import aws
from util.tests import helper as util_helper


class AccountUtilTest(TestCase):
    """Account util test cases."""

    def test_create_new_machine_images(self):
        """Test that new machine images are saved to the DB."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        account = AwsAccount(account_arn=arn, aws_account_id=aws_account_id)
        account.save()

        region = random.choice(util_helper.SOME_AWS_REGIONS)
        running_instances = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        ami_id = running_instances[region][0]['ImageId']

        result = util.create_new_machine_images(account, running_instances)

        amis = AwsMachineImage.objects.filter(account=account).all()

        self.assertEqual(result, [ami_id])
        for ami in amis:
            self.assertEqual(ami.ec2_ami_id, ami_id)

    def test_create_new_machine_images_with_windows_image(self):
        """Test that new windows machine images are marked appropriately."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        account = AwsAccount(account_arn=arn, aws_account_id=aws_account_id)
        account.save()

        region = random.choice(util_helper.SOME_AWS_REGIONS)
        running_instances = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        running_instances[region][0]['Platform'] = 'Windows'
        ami_id = running_instances[region][0]['ImageId']

        result = util.create_new_machine_images(account, running_instances)

        amis = AwsMachineImage.objects.filter(account=account).all()

        self.assertEqual(result, [ami_id])
        for ami in amis:
            self.assertEqual(ami.ec2_ami_id, ami_id)
            self.assertTrue(ami.is_windows)

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

    @patch('account.util.kombu')
    def test_add_messages_to_queue(self, mock_kombu):
        """Test that messages get added to a message queue."""
        queue_name = 'Test Queue'
        region = random.choice(util_helper.SOME_AWS_REGIONS)
        instance = util_helper.generate_dummy_describe_instance()
        instances_data = {region: [instance]}
        ami_list = [instance['ImageId']]

        messages = util.generate_aws_ami_messages(instances_data, ami_list)
        mock_routing_key = queue_name
        mock_body = messages[0]

        mock_exchange = mock_kombu.Exchange.return_value
        mock_queue = mock_kombu.Queue.return_value
        mock_conn = mock_kombu.Connection.return_value
        mock_with_conn = mock_conn.__enter__.return_value
        mock_producer = mock_with_conn.Producer.return_value
        mock_pub = mock_producer.publish

        util.add_messages_to_queue(queue_name, messages)

        mock_pub.assert_called_with(
            mock_body,
            retry=True,
            exchange=mock_exchange,
            routing_key=mock_routing_key,
            declare=[mock_queue]
        )

    def prepare_mock_kombu_for_consuming(self, mock_kombu):
        """Prepare mock_kombu with mock messages."""
        mock_conn = mock_kombu.Connection.return_value
        mock_with_conn = mock_conn.__enter__.return_value
        mock_consumer = mock_with_conn.SimpleQueue.return_value
        mock_messages = [Mock(), Mock()]
        mock_consumer.get_nowait.side_effect = mock_messages + [Empty]
        return mock_messages

    @patch('account.util.kombu')
    def test_read_messages_from_queue_until_empty(self, mock_kombu):
        """Test that all messages are read from a message queue."""
        mock_messages = self.prepare_mock_kombu_for_consuming(mock_kombu)
        queue_name = 'Test Queue'
        expected_results = [mock_messages[0].payload, mock_messages[1].payload]
        actual_results = util.read_messages_from_queue(queue_name, 5)
        self.assertEqual(actual_results, expected_results)
        mock_messages[0].ack.assert_called_once()
        mock_messages[1].ack.assert_called_once()

    @patch('account.util.kombu')
    def test_read_messages_from_queue_once(self, mock_kombu):
        """Test that one message is read from a message queue."""
        mock_messages = self.prepare_mock_kombu_for_consuming(mock_kombu)
        queue_name = 'Test Queue'
        expected_results = [mock_messages[0].payload]
        actual_results = util.read_messages_from_queue(queue_name)
        self.assertEqual(actual_results, expected_results)
        mock_messages[0].ack.assert_called_once()
        mock_messages[1].ack.assert_not_called()
