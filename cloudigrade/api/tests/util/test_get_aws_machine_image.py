"""Collection of tests for api.util.get_aws_machine_image."""
from django.test import TestCase

import util.aws.sqs
from api import util
from api.models import AwsMachineImage
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class GetAwsMachineImageTest(TestCase):
    """Test cases for api.util.get_aws_machine_image."""

    def test_objects_exist(self):
        """Test happy path when both objects exist."""
        ec2_ami_id = util_helper.generate_dummy_image_id()
        expected_machine_image = api_helper.generate_aws_image(ec2_ami_id=ec2_ami_id)
        expected_aws_machine_image = expected_machine_image.content_object

        result = util.get_aws_machine_image(ec2_ami_id)
        self.assertEqual(expected_aws_machine_image, result[0])
        self.assertEqual(expected_machine_image, result[1])

    def test_without_aws_machine_image(self):
        """Test when AwsMachineImage does not exist."""
        ec2_ami_id = util_helper.generate_dummy_image_id()
        result = util.get_aws_machine_image(ec2_ami_id)
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])

    def test_without_machine_image(self):
        """Test when MachineImage does not exist."""
        ec2_ami_id = util_helper.generate_dummy_image_id()
        AwsMachineImage.objects.create(
            owner_aws_account_id=util_helper.generate_dummy_aws_account_id(),
            ec2_ami_id=ec2_ami_id,
        )
        result = util.get_aws_machine_image(ec2_ami_id)
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
