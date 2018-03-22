"""Collection of tests for utils in the account app."""
import random
import uuid
from unittest.mock import patch

from django.test import TestCase

from account import AWS_PROVIDER_STRING, util
from account.models import AwsAccount, AwsMachineImage
from util import aws
from util.tests import helper as util_helper


def mock_publish(body, exchange, routing_key, declare):
    """Mock queue publish function."""
    return True


class AccountUtilTest(TestCase):
    """Account util test cases."""

    def test_create_new_machine_images(self):
        """Test that new machine images are saved to the DB."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        account = AwsAccount(account_arn=arn, aws_account_id=aws_account_id)
        account.save()

        region = f'region-{uuid.uuid4()}'
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

        region = f'region-{uuid.uuid4()}'
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
            self.assertEqual(ami.platform, ami.TYPE.Windows)

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

    def test_add_messages_to_queue(self):
        """Test that messages get added to a message queue."""
        queue_name = 'Test Queue'
        region = random.choice(util_helper.SOME_AWS_REGIONS)
        instance = util_helper.generate_dummy_describe_instance()
        instances_data = {region: [instance]}
        ami_list = [instance['ImageId']]

        messages = util.generate_aws_ami_messages(instances_data, ami_list)
        mock_routing_key = queue_name
        mock_body = messages[0]

        expected = {ami_list[0]: True}

        with patch.object(util, 'kombu') as mock_kombu:
            mock_exchange = mock_kombu.Exchange.return_value
            mock_queue = mock_kombu.Queue.return_value
            mock_conn = mock_kombu.Connection.return_value
            mock_with_conn = mock_conn.__enter__.return_value
            mock_producer = mock_with_conn.Producer.return_value
            mock_pub = mock_producer.publish
            mock_pub.side_effect = mock_publish

            result = util.add_messages_to_queue(queue_name, messages)

        mock_pub.assert_called_with(
            mock_body,
            exchange=mock_exchange,
            routing_key=mock_routing_key,
            declare=[mock_queue]
        )

        self.assertEqual(result, expected)

    def test_add_messages_to_queue_with_windows_image(self):
        """Test that Windows machine images are not added to a queue."""
        queue_name = 'Test Queue'
        region = random.choice(util_helper.SOME_AWS_REGIONS)
        instance = util_helper.generate_dummy_describe_instance()
        instance['Platform'] = 'Windows'
        instances_data = {region: [instance]}
        ami_list = [instance['ImageId']]

        messages = util.generate_aws_ami_messages(instances_data, ami_list)
        expected = {}

        with patch.object(util, 'kombu') as mock_kombu:
            mock_conn = mock_kombu.Connection.return_value
            mock_with_conn = mock_conn.__enter__.return_value
            mock_producer = mock_with_conn.Producer.return_value
            mock_pub = mock_producer.publish
            mock_pub.side_effect = mock_publish

            result = util.add_messages_to_queue(queue_name, messages)

        mock_pub.assert_not_called()
        self.assertEqual(result, expected)
