"""Collection of tests for api.clouds.aws.util.create_new_machine_images."""
from unittest.mock import Mock, patch

from django.test import TestCase

from api.clouds.aws import util
from api.clouds.aws.models import AwsMachineImage
from api.tests import helper as api_helper
from util import aws
from util.tests import helper as util_helper


class CreateNewMachineImagesTest(TestCase):
    """Test cases for api.util.create_new_machine_images."""

    def test_create_new_machine_images(self):
        """Test that new machine images are saved to the DB."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        api_helper.generate_cloud_account(arn=arn, aws_account_id=aws_account_id)

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
            result = util.create_new_machine_images(mock_session, instances_data)
            mock_describe_images.assert_called_with(mock_session, {ami_id}, region)

        self.assertEqual(result, [ami_id])

        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].ec2_ami_id, ami_id)

    def test_create_new_machine_images_with_windows_image(self):
        """Test that new windows machine images are marked appropriately."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        api_helper.generate_cloud_account(arn=arn, aws_account_id=aws_account_id)

        region = util_helper.get_random_region()
        instances_data = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                )
            ]
        }
        instances_data[region][0]["Platform"] = "Windows"
        ami_id = instances_data[region][0]["ImageId"]

        mock_session = Mock()
        described_amis = util_helper.generate_dummy_describe_image(
            image_id=ami_id, owner_id=aws_account_id
        )

        with patch.object(util.aws, "describe_images") as mock_describe_images:
            mock_describe_images.return_value = [described_amis]
            result = util.create_new_machine_images(mock_session, instances_data)
            mock_describe_images.assert_called_with(mock_session, {ami_id}, region)

        self.assertEqual(result, [ami_id])

        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].ec2_ami_id, ami_id)
        self.assertEqual(images[0].platform, AwsMachineImage.WINDOWS)
