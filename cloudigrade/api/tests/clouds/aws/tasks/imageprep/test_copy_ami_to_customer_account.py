"""Collection of tests for aws.tasks.cloudtrail.copy_ami_to_customer_account."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.test import TestCase

from api.clouds.aws import tasks
from api.models import MachineImage
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class CopyAmiToCustomerAccountTest(TestCase):
    """Celery task 'copy_ami_to_customer_account' test cases."""

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_to_customer_account_success(self, mock_aws):
        """Assert that the task copies image using appropriate boto calls."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()

        api_helper.generate_image(ec2_ami_id=reference_ami_id)

        new_ami_id = mock_aws.copy_ami.return_value

        with patch.object(
            tasks.imageprep, "copy_ami_snapshot"
        ) as mock_copy_ami_snapshot:
            tasks.copy_ami_to_customer_account(arn, reference_ami_id, source_region)
            mock_copy_ami_snapshot.delay.assert_called_with(
                arn, new_ami_id, source_region, reference_ami_id
            )

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )
        reference_ami = mock_aws.get_ami.return_value
        mock_aws.copy_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami.id, source_region
        )

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_to_customer_account_marketplace(self, mock_aws):
        """Assert that the task marks marketplace image as inspected."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()

        image = api_helper.generate_image(
            ec2_ami_id=reference_ami_id, status=MachineImage.INSPECTING
        )

        mock_reference_ami = Mock()
        mock_reference_ami.public = True
        mock_aws.get_ami.return_value = mock_reference_ami

        mock_aws.copy_ami.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "InvalidRequest",
                    "Message": "Images with EC2 BillingProduct codes cannot "
                    "be copied to another AWS account",
                }
            },
            operation_name=Mock(),
        )

        tasks.copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )

        image.refresh_from_db()
        aws_image = image.content_object
        aws_image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.INSPECTED)
        self.assertTrue(aws_image.aws_marketplace_image)

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_to_customer_account_marketplace_with_dot_error(self, mock_aws):
        """Assert that the task marks marketplace image as inspected."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()
        image = api_helper.generate_image(
            ec2_ami_id=reference_ami_id, status=MachineImage.INSPECTING
        )

        mock_aws.copy_ami.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "InvalidRequest",
                    "Message": "Images with EC2 BillingProduct codes cannot "
                    "be copied to another AWS account.",
                }
            },
            operation_name=Mock(),
        )

        tasks.copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )
        image.refresh_from_db()
        aws_image = image.content_object
        aws_image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.INSPECTED)
        self.assertTrue(aws_image.aws_marketplace_image)

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_to_customer_account_missing_image(self, mock_aws):
        """Assert early return if the AwsMachineImage doesn't exist."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        region = util_helper.get_random_region()
        tasks.copy_ami_to_customer_account(arn, reference_ami_id, region)
        mock_aws.get_session.assert_not_called()

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_to_customer_account_community(self, mock_aws):
        """Assert that the task marks community image as inspected."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()
        image = api_helper.generate_image(
            ec2_ami_id=reference_ami_id, status=MachineImage.INSPECTING
        )
        mock_aws.copy_ami.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "InvalidRequest",
                    "Message": "Images from AWS Marketplace cannot be copied "
                    "to another AWS account",
                }
            },
            operation_name=Mock(),
        )
        tasks.copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )

        image.refresh_from_db()
        aws_image = image.content_object
        aws_image.refresh_from_db()

        self.assertEqual(image.status, image.INSPECTED)
        self.assertTrue(aws_image.aws_marketplace_image)

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_to_customer_account_private_no_copy(self, mock_aws):
        """Assert that the task marks private (no copy) image as in error."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()

        image = api_helper.generate_image(
            ec2_ami_id=reference_ami_id, status=MachineImage.INSPECTING
        )

        mock_reference_ami = Mock()
        mock_reference_ami.public = False
        mock_aws.get_ami.return_value = mock_reference_ami

        mock_aws.copy_ami.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "InvalidRequest",
                    "Message": "You do not have permission to access the "
                    "storage of this ami",
                }
            },
            operation_name=Mock(),
        )

        tasks.copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        image.refresh_from_db()

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )
        self.assertEqual(image.status, MachineImage.ERROR)

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_to_customer_account_private_no_copy_dot_error(self, mock_aws):
        """Assert that the task marks private (no copy) image as in error."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()
        image = api_helper.generate_image(
            ec2_ami_id=reference_ami_id, status=MachineImage.INSPECTING
        )
        mock_reference_ami = Mock()
        mock_reference_ami.public = False
        mock_aws.get_ami.return_value = mock_reference_ami

        mock_aws.copy_ami.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "InvalidRequest",
                    "Message": "You do not have permission to access the "
                    "storage of this ami.",
                }
            },
            operation_name=Mock(),
        )

        tasks.copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )
        image.refresh_from_db()

        self.assertEqual(image.status, MachineImage.ERROR)

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_to_customer_account_not_marketplace(self, mock_aws):
        """Assert that the task fails when non-marketplace error occurs."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        source_region = util_helper.get_random_region()

        api_helper.generate_image(ec2_ami_id=reference_ami_id)

        mock_aws.copy_ami.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ItIsAMystery", "Message": "Mystery Error"}
            },
            operation_name=Mock(),
        )

        with self.assertRaises(RuntimeError) as e:
            tasks.copy_ami_to_customer_account(arn, reference_ami_id, source_region)

        self.assertIn("ClientError", e.exception.args[0])
        self.assertIn("ItIsAMystery", e.exception.args[0])
        self.assertIn("Mystery Error", e.exception.args[0])

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(
            mock_aws.get_session.return_value, reference_ami_id, source_region
        )

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_to_customer_account_save_error_when_image_load_fails(
        self, mock_aws
    ):
        """Assert that we save error status if image load fails."""
        arn = util_helper.generate_dummy_arn()
        reference_ami_id = util_helper.generate_dummy_image_id()
        snapshot_region = util_helper.get_random_region()
        image = api_helper.generate_image(ec2_ami_id=reference_ami_id)

        mock_aws.get_ami.return_value = None
        with patch.object(tasks.imageprep, "copy_ami_snapshot") as mock_copy:
            tasks.copy_ami_to_customer_account(arn, reference_ami_id, snapshot_region)
            mock_copy.delay.assert_not_called()
        mock_aws.copy_ami.assert_not_called()

        image.refresh_from_db()
        self.assertEquals(image.status, image.ERROR)
