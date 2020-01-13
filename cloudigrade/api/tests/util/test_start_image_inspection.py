"""Collection of tests for api.util.start_image_inspection."""
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase

import util.aws.sqs
from api import util
from api.models import MachineImageInspectionStart
from api.tests import helper as api_helper


class StartImageInspectionTest(TestCase):
    """Test cases for api.util.start_image_inspection."""

    @patch("api.tasks.copy_ami_snapshot")
    def test_start_image_inspection_runs(self, mock_copy):
        """Test that inspection skips for marketplace images."""
        image = api_helper.generate_aws_image()
        mock_arn = Mock()
        mock_region = Mock()
        util.start_image_inspection(
            mock_arn, image.content_object.ec2_ami_id, mock_region
        )
        mock_copy.delay.assert_called_with(
            mock_arn, image.content_object.ec2_ami_id, mock_region
        )
        image.refresh_from_db()
        self.assertEqual(image.status, image.PREPARING)
        self.assertTrue(
            MachineImageInspectionStart.objects.filter(
                machineimage__id=image.id
            ).exists()
        )

    @patch("api.tasks.copy_ami_snapshot")
    def test_start_image_inspection_marketplace_skips(self, mock_copy):
        """Test that inspection skips for marketplace images."""
        image = api_helper.generate_aws_image(is_marketplace=True)
        util.start_image_inspection(None, image.content_object.ec2_ami_id, None)
        mock_copy.delay.assert_not_called()
        image.refresh_from_db()
        self.assertEqual(image.status, image.INSPECTED)

    @patch("api.tasks.copy_ami_snapshot")
    def test_start_image_inspection_cloud_access_skips(self, mock_copy):
        """Test that inspection skips for Cloud Access images."""
        image = api_helper.generate_aws_image(is_cloud_access=True)
        util.start_image_inspection(None, image.content_object.ec2_ami_id, None)
        mock_copy.delay.assert_not_called()
        image.refresh_from_db()
        self.assertEqual(image.status, image.INSPECTED)

    @patch("api.tasks.copy_ami_snapshot")
    def test_start_image_inspection_exceed_max_allowed(self, mock_copy):
        """Test that inspection stops when max allowed attempts is exceeded."""
        image = api_helper.generate_aws_image()
        for _ in range(0, settings.MAX_ALLOWED_INSPECTION_ATTEMPTS + 1):
            MachineImageInspectionStart.objects.create(machineimage=image)
        util.start_image_inspection(None, image.content_object.ec2_ami_id, None)
        mock_copy.delay.assert_not_called()
        image.refresh_from_db()
        self.assertEqual(image.status, image.ERROR)
