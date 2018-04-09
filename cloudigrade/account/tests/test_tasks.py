"""Collection of tests for celery tasks."""
import random
import uuid
from unittest.mock import patch

from celery.exceptions import Retry
from django.test import TestCase

from account.models import AwsAccount, AwsMachineImage
from account.tasks import copy_ami_snapshot
from util.exceptions import (AwsSnapshotCopyLimitError,
                             AwsSnapshotEncryptedError,
                             AwsSnapshotNotOwnedError)
from util.tests import helper as util_helper


class AccountCeleryTaskTest(TestCase):
    """Account app Celery task test cases."""

    @patch('account.tasks.aws')
    def test_copy_ami_snapshot_success(self, mock_aws):
        """Assert that the snapshot copy task succeeds."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_image_id = str(uuid.uuid4())
        mock_image = util_helper.generate_mock_image(mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]['Ebs']['SnapshotId']
        mock_new_snapshot_id = util_helper.generate_mock_snapshot_id()
        mock_session = mock_aws.boto3.Session.return_value

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.copy_snapshot.return_value = mock_new_snapshot_id

        copy_ami_snapshot(mock_arn, mock_image_id, mock_region)

        mock_aws.get_session.asssert_called_with(mock_arn)
        mock_aws.get_ami.asssert_called_with(
            mock_session,
            mock_image_id,
            mock_region
        )
        mock_aws.get_ami_snapshot_id.asssert_called_with(mock_image)
        mock_aws.change_snapshot_ownership.asssert_called_with(
            mock_session,
            mock_snapshot_id,
            mock_region,
            operation='Add'
        )
        mock_aws.copy_snapshot.asssert_called_with(
            mock_snapshot_id,
            mock_region
        )

    @patch('account.tasks.aws')
    def test_copy_ami_snapshot_encrypted(self, mock_aws):
        """Assert that the task marks the image as encrypted in the DB."""
        mock_account_id = util_helper.generate_dummy_aws_account_id()
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_arn = util_helper.generate_dummy_arn(mock_account_id, mock_region)

        mock_image_id = str(uuid.uuid4())
        mock_image = util_helper.generate_mock_image(mock_image_id)
        mock_session = mock_aws.boto3.Session.return_value

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.side_effect = AwsSnapshotEncryptedError()
        account = AwsAccount(
            aws_account_id=mock_account_id,
            account_arn=mock_arn
        )
        account.save()
        ami = AwsMachineImage.objects.create(
            account=account,
            is_windows=False,
            ec2_ami_id=mock_image_id
        )

        ami.save()

        with self.assertRaises(AwsSnapshotEncryptedError):
            copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
            self.assertTrue(ami.is_encrypted)

    @patch('account.tasks.aws')
    def test_copy_ami_snapshot_retry_on_copy_limit(self, mock_aws):
        """Assert that the copy task is retried."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_image_id = str(uuid.uuid4())
        mock_image = util_helper.generate_mock_image(mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]['Ebs']['SnapshotId']
        mock_session = mock_aws.boto3.Session.return_value

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.change_snapshot_ownership.return_value = True
        mock_aws.copy_snapshot.side_effect = AwsSnapshotCopyLimitError()

        with patch.object(copy_ami_snapshot, 'retry') as mock_retry:
            mock_retry.side_effect = Retry()

            with self.assertRaises(Retry):
                copy_ami_snapshot(mock_arn, mock_image_id, mock_region)

    @patch('account.tasks.aws')
    def test_copy_ami_snapshot_retry_on_ownership_not_verified(self, mock_aws):
        """Assert that the snapshot copy task fails."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_image_id = str(uuid.uuid4())
        mock_image = util_helper.generate_mock_image(mock_image_id)
        block_mapping = mock_image.block_device_mappings
        mock_snapshot_id = block_mapping[0]['Ebs']['SnapshotId']
        mock_session = mock_aws.boto3.Session.return_value

        mock_aws.get_session.return_value = mock_session
        mock_aws.get_ami.return_value = mock_image
        mock_aws.get_ami_snapshot_id.return_value = mock_snapshot_id
        mock_aws.copy_snapshot.side_effect = AwsSnapshotNotOwnedError()

        with self.assertRaises(AwsSnapshotNotOwnedError):
            copy_ami_snapshot(mock_arn, mock_image_id, mock_region)
