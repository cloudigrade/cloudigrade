"""Collection of tests for utils in the account app."""
import random

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
