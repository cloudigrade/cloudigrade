"""Collection of tests for aws.tasks.cloudtrail.copy_ami_snapshot."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from celery.exceptions import Retry
from django.test import TestCase

from api.clouds.aws import tasks
from api.clouds.aws.models import AwsMachineImageCopy
from api.tests import helper as account_helper
from util.exceptions import AwsSnapshotCopyLimitError, AwsSnapshotNotOwnedError
from util.tests import helper as util_helper


class CopyAmiSnapshotTest(TestCase):
    """Celery task 'copy_ami_snapshot' test cases."""

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_snapshot_success(self, mock_aws):
        """Assert that the snapshot copy task succeeds."""
        mock_session = mock_aws.boto3.Session.return_value
        mock_account_id = mock_aws.get_session_account_id.return_value

        mock_arn = util_helper.generate_dummy_arn()
        mock_region = util_helper.get_random_region()
        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        account_helper.generate_image(ec2_ami_id=mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]["Ebs"]["SnapshotId"]
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id, owner_id=mock_account_id
        )
        mock_new_snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot
        mock_aws.copy_snapshot.return_value = mock_new_snapshot_id

        with patch.object(tasks.imageprep, "create_volume") as mock_create_volume:
            with patch.object(
                tasks.imageprep, "remove_snapshot_ownership"
            ) as mock_remove_snapshot_ownership:
                tasks.copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
                mock_create_volume.delay.assert_called_with(
                    mock_image_id, mock_new_snapshot_id
                )
                mock_remove_snapshot_ownership.delay.assert_called_with(
                    mock_arn,
                    mock_snapshot_id,
                    mock_region,
                    mock_new_snapshot_id,
                )

        mock_aws.get_session.assert_called_with(mock_arn)
        mock_aws.get_ami.assert_called_with(mock_session, mock_image_id, mock_region)
        mock_aws.get_ami_snapshot_id.assert_called_with(mock_image)
        mock_aws.add_snapshot_ownership.assert_called_with(mock_snapshot)
        mock_aws.copy_snapshot.assert_called_with(mock_snapshot_id, mock_region)

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_snapshot_success_with_reference(self, mock_aws):
        """Assert the snapshot copy task succeeds using a reference AMI ID."""
        mock_session = mock_aws.boto3.Session.return_value
        mock_account_id = mock_aws.get_session_account_id.return_value

        account = account_helper.generate_cloud_account()
        arn = account.content_object.account_arn

        region = util_helper.get_random_region()
        new_image_id = util_helper.generate_dummy_image_id()
        # unlike non-reference calls to copy_ami_snapshot, we do NOT want to
        # call "account_helper.generate_aws_image(ec2_ami_id=new_image_id)"
        # here because cloudigrade has only seen the reference, not the new.
        mock_image = util_helper.generate_mock_image(new_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]["Ebs"]["SnapshotId"]
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id, owner_id=mock_account_id
        )
        mock_new_snapshot_id = util_helper.generate_dummy_snapshot_id()

        # This is the original ID of a private/shared image.
        # It would have been saved to our DB upon initial discovery.
        reference_image = account_helper.generate_image()
        reference_image_id = reference_image.content_object.ec2_ami_id

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot
        mock_aws.copy_snapshot.return_value = mock_new_snapshot_id

        with patch.object(
            tasks.imageprep, "create_volume"
        ) as mock_create_volume, patch.object(
            tasks.imageprep, "remove_snapshot_ownership"
        ) as mock_remove_snapshot_ownership:
            tasks.copy_ami_snapshot(arn, new_image_id, region, reference_image_id)
            # arn, customer_snapshot_id, snapshot_region, snapshot_copy_id
            mock_remove_snapshot_ownership.delay.assert_called_with(
                arn, mock_snapshot_id, region, mock_new_snapshot_id
            )
            mock_create_volume.delay.assert_called_with(
                reference_image_id, mock_new_snapshot_id
            )

        mock_aws.get_session.assert_called_with(arn)
        mock_aws.get_ami.assert_called_with(mock_session, new_image_id, region)
        mock_aws.get_ami_snapshot_id.assert_called_with(mock_image)
        mock_aws.add_snapshot_ownership.assert_called_with(mock_snapshot)
        mock_aws.copy_snapshot.assert_called_with(mock_snapshot_id, region)

        # Verify that the copy object was stored correctly to reference later.
        copied_image = AwsMachineImageCopy.objects.get(ec2_ami_id=new_image_id)
        self.assertIsNotNone(copied_image)
        self.assertEqual(
            copied_image.reference_awsmachineimage.ec2_ami_id,
            reference_image_id,
        )

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_snapshot_encrypted(self, mock_aws):
        """Assert that the task marks the image as encrypted in the DB."""
        mock_account_id = util_helper.generate_dummy_aws_account_id()
        mock_region = util_helper.get_random_region()
        mock_arn = util_helper.generate_dummy_arn(mock_account_id, mock_region)

        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        mock_snapshot_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id, encrypted=True
        )
        mock_session = mock_aws.boto3.Session.return_value

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot

        ami = account_helper.generate_image(ec2_ami_id=mock_image_id)

        with patch.object(tasks, "create_volume") as mock_create_volume:
            tasks.copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            ami.refresh_from_db()
            self.assertTrue(ami.is_encrypted)
            self.assertEqual(ami.status, ami.ERROR)
            mock_create_volume.delay.assert_not_called()

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_snapshot_retry_on_copy_limit(self, mock_aws):
        """Assert that the copy task is retried."""
        mock_session = mock_aws.boto3.Session.return_value
        mock_account_id = mock_aws.get_session_account_id.return_value

        mock_arn = util_helper.generate_dummy_arn()
        mock_region = util_helper.get_random_region()
        mock_image_id = util_helper.generate_dummy_image_id()
        account_helper.generate_image(ec2_ami_id=mock_image_id)
        mock_image = util_helper.generate_mock_image(mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]["Ebs"]["SnapshotId"]
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id, owner_id=mock_account_id
        )

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot
        mock_aws.add_snapshot_ownership.return_value = True
        mock_aws.copy_snapshot.side_effect = AwsSnapshotCopyLimitError()

        with patch.object(tasks, "create_volume") as mock_create_volume, patch.object(
            tasks.copy_ami_snapshot, "retry"
        ) as mock_retry:
            mock_retry.side_effect = Retry()
            with self.assertRaises(Retry):
                tasks.copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            mock_create_volume.delay.assert_not_called()

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_snapshot_missing_image(self, mock_aws):
        """Assert early return if the AwsMachineImage doesn't exist."""
        arn = util_helper.generate_dummy_arn()
        ec2_ami_id = util_helper.generate_dummy_image_id()
        region = util_helper.get_random_region()
        tasks.copy_ami_snapshot(arn, ec2_ami_id, region)
        mock_aws.get_session.assert_not_called()

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_snapshot_retry_on_ownership_not_verified(self, mock_aws):
        """Assert that the snapshot copy task fails."""
        mock_session = mock_aws.boto3.Session.return_value
        mock_account_id = mock_aws.get_session_account_id.return_value

        mock_arn = util_helper.generate_dummy_arn()
        mock_region = util_helper.get_random_region()
        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        account_helper.generate_image(ec2_ami_id=mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]["Ebs"]["SnapshotId"]
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id, owner_id=mock_account_id
        )

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot
        mock_aws.add_snapshot_ownership.side_effect = AwsSnapshotNotOwnedError()

        with patch.object(tasks, "create_volume") as mock_create_volume, patch.object(
            tasks.copy_ami_snapshot, "retry"
        ) as mock_retry:
            mock_retry.side_effect = Retry()
            with self.assertRaises(Retry):
                tasks.copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            mock_create_volume.delay.assert_not_called()

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_snapshot_private_shared(self, mock_aws):
        """Assert that the task copies the image when it is private/shared."""
        mock_account_id = util_helper.generate_dummy_aws_account_id()
        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session_account_id.return_value = mock_account_id

        # the account id to use as the private shared image owner
        other_account_id = util_helper.generate_dummy_aws_account_id()

        mock_region = util_helper.get_random_region()
        mock_arn = util_helper.generate_dummy_arn(mock_account_id, mock_region)

        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        mock_snapshot_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot = util_helper.generate_mock_snapshot(
            mock_snapshot_id, encrypted=False, owner_id=other_account_id
        )

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.return_value = mock_snapshot

        account_helper.generate_image(ec2_ami_id=mock_image_id)

        with patch.object(
            tasks.imageprep, "create_volume"
        ) as mock_create_volume, patch.object(
            tasks.imageprep, "copy_ami_to_customer_account"
        ) as mock_copy_ami_to_customer_account:
            tasks.copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            mock_create_volume.delay.assert_not_called()
            mock_copy_ami_to_customer_account.delay.assert_called_with(
                mock_arn, mock_image_id, mock_region
            )

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_snapshot_marketplace(self, mock_aws):
        """Assert that a suspected marketplace image is checked."""
        mock_account_id = util_helper.generate_dummy_aws_account_id()
        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session_account_id.return_value = mock_account_id

        mock_region = util_helper.get_random_region()
        mock_arn = util_helper.generate_dummy_arn(mock_account_id, mock_region)

        mock_image_id = util_helper.generate_dummy_image_id()
        mock_image = util_helper.generate_mock_image(mock_image_id)
        mock_snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.side_effect = ClientError(
            error_response={"Error": {"Code": "InvalidSnapshot.NotFound"}},
            operation_name=Mock(),
        )

        account_helper.generate_image(ec2_ami_id=mock_image_id)

        with patch.object(
            tasks.imageprep, "create_volume"
        ) as mock_create_volume, patch.object(
            tasks.imageprep, "copy_ami_to_customer_account"
        ) as mock_copy_ami_to_customer_account:
            tasks.copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            mock_create_volume.delay.assert_not_called()
            mock_copy_ami_to_customer_account.delay.assert_called_with(
                mock_arn, mock_image_id, mock_region
            )

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_snapshot_not_marketplace(self, mock_aws):
        """Assert that an exception is raised when there is an error."""
        mock_account_id = util_helper.generate_dummy_aws_account_id()
        mock_session = mock_aws.boto3.Session.return_value
        mock_aws.get_session_account_id.return_value = mock_account_id

        mock_region = util_helper.get_random_region()
        mock_arn = util_helper.generate_dummy_arn(mock_account_id, mock_region)

        mock_image_id = util_helper.generate_dummy_image_id()
        account_helper.generate_image(ec2_ami_id=mock_image_id)
        mock_image = util_helper.generate_mock_image(mock_image_id)
        mock_snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.get_snapshot.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ItIsAMystery", "Message": "Mystery Error"}
            },
            operation_name=Mock(),
        )

        with self.assertRaises(RuntimeError) as e:
            tasks.copy_ami_snapshot(mock_arn, mock_image_id, mock_region)

        self.assertIn("ClientError", e.exception.args[0])
        self.assertIn("ItIsAMystery", e.exception.args[0])
        self.assertIn("Mystery Error", e.exception.args[0])

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_snapshot_save_error_when_image_load_fails(self, mock_aws):
        """Assert that we save error status if image load fails."""
        arn = util_helper.generate_dummy_arn()
        ami_id = util_helper.generate_dummy_image_id()
        snapshot_region = util_helper.get_random_region()
        image = account_helper.generate_image(ec2_ami_id=ami_id)

        mock_aws.get_ami.return_value = None

        with patch.object(tasks, "create_volume") as mock_create_volume, patch.object(
            tasks, "copy_ami_to_customer_account"
        ) as mock_copy_ami_to_customer_account:
            tasks.copy_ami_snapshot(arn, ami_id, snapshot_region)
            mock_create_volume.delay.assert_not_called()
            mock_copy_ami_to_customer_account.delay.assert_not_called()

        image.refresh_from_db()
        self.assertEquals(image.status, image.ERROR)

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_copy_ami_snapshot_save_error_when_image_snapshot_id_get_fails(
        self, mock_aws
    ):
        """Assert that we save error status if snapshot id is not available."""
        arn = util_helper.generate_dummy_arn()
        ami_id = util_helper.generate_dummy_image_id()
        snapshot_region = util_helper.get_random_region()
        image = account_helper.generate_image(ec2_ami_id=ami_id)

        mock_aws.get_ami.return_value = image
        mock_aws.get_ami_snapshot_id.return_value = None

        with patch.object(tasks, "create_volume") as mock_create_volume, patch.object(
            tasks, "copy_ami_to_customer_account"
        ) as mock_copy_ami_to_customer_account:
            tasks.copy_ami_snapshot(arn, ami_id, snapshot_region)
            mock_create_volume.delay.assert_not_called()
            mock_copy_ami_to_customer_account.delay.assert_not_called()

        image.refresh_from_db()
        self.assertEquals(image.status, image.ERROR)
