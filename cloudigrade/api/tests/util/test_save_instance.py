"""Collection of tests for api.util.save_instance."""
from unittest.mock import Mock, patch

from django.test import TestCase

import util.aws.sqs
from api import util
from api.clouds.aws.models import AwsMachineImage
from api.models import MachineImage
from api.tests import helper as api_helper
from util import aws
from util.tests import helper as util_helper


class SaveInstanceTest(TestCase):
    """Test cases for api.util.save_instance."""

    def test_save_instance_with_unavailable_image(self):
        """Test that save instance events also writes image on instance."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        account = api_helper.generate_aws_account(
            arn=arn, aws_account_id=aws_account_id
        )

        region = util_helper.get_random_region()
        instances_data = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        ami_id = instances_data[region][0]["ImageId"]

        awsinstance = util.save_instance(account, instances_data[region][0], region)
        instance = awsinstance.instance.get()

        self.assertEqual(instance.machine_image.content_object.ec2_ami_id, ami_id)
        self.assertEqual(instance.machine_image.status, MachineImage.UNAVAILABLE)

    def test_save_instance_with_missing_machineimage(self):
        """
        Test that save_instance works around a missing MachineImage.

        This is a use case that we *shouldn't* need, but until we identify how
        exactly AwsMachineImage objects are being saved without their matching
        MachineImage objects, we have this workaround to create the
        MachineImage at the time it is needed.
        """
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        account = api_helper.generate_aws_account(
            arn=arn, aws_account_id=aws_account_id
        )

        region = util_helper.get_random_region()
        instances_data = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        ami_id = instances_data[region][0]["ImageId"]

        # Create the AwsMachineImage without its paired MachineImage.
        aws_machine_image = AwsMachineImage.objects.create(
            owner_aws_account_id=util_helper.generate_dummy_aws_account_id(),
            ec2_ami_id=ami_id,
            platform="none",
        )
        # Verify that the MachineImage was *not* created before proceeding.
        with self.assertRaises(MachineImage.DoesNotExist):
            aws_machine_image.machine_image.get()

        awsinstance = util.save_instance(account, instances_data[region][0], region)
        instance = awsinstance.instance.get()

        self.assertEqual(instance.machine_image.content_object.ec2_ami_id, ami_id)
        self.assertEqual(instance.machine_image.status, MachineImage.UNAVAILABLE)

    def test_save_instance_with_available_image(self):
        """Test that save instance events also writes image on instance."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        account = api_helper.generate_aws_account(
            arn=arn, aws_account_id=aws_account_id
        )

        region = util_helper.get_random_region()
        instances_data = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        ami_id = instances_data[region][0]["ImageId"]

        mock_session = Mock()
        described_amis = util_helper.generate_dummy_describe_image(
            image_id=ami_id, owner_id=aws_account_id
        )

        with patch.object(util.aws, "describe_images") as mock_describe_images:
            mock_describe_images.return_value = [described_amis]
            util.create_new_machine_images(mock_session, instances_data)
            mock_describe_images.assert_called_with(mock_session, {ami_id}, region)
        awsinstance = util.save_instance(account, instances_data[region][0], region)
        instance = awsinstance.instance.get()
        self.assertEqual(instance.machine_image.content_object.ec2_ami_id, ami_id)
        self.assertEqual(instance.machine_image.status, MachineImage.PENDING)
