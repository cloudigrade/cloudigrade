"""Collection of tests for custom Django model logic."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.test import TestCase

from api import models
from api.tests import helper
from util.aws import sts
from util.exceptions import CloudTrailCannotStopLogging
from util.tests import helper as util_helper


class AwsCloudAccountModelTest(TestCase):
    """AwsCloudAccount Model Test Cases."""

    def setUp(self):
        """Set up basic aws account."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        self.role = util_helper.generate_dummy_role()
        self.account = helper.generate_aws_account(
            aws_account_id=aws_account_id,
            arn=arn,
            name='test'
        )

    def test_delete_succeeds(self):
        """Test that an account is deleted if there are no errors."""
        with patch.object(sts, 'boto3') as mock_boto3,\
                patch.object(models, 'disable_cloudtrail'):
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            self.account.delete()
            self.assertEqual(0, models.AwsCloudAccount.objects.count())

    def test_delete_succeeds_on_access_denied_exception(self):
        """Test that the account is deleted on CloudTrail access denied."""
        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDeniedException'}},
            operation_name=Mock(),
        )

        with patch.object(models, 'disable_cloudtrail') as mock_cloudtrail,\
                patch.object(sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error

            self.account.delete()

        self.assertEqual(0, models.AwsCloudAccount.objects.count())

    def test_delete_fails_on_other_cloudtrail_exception(self):
        """Test that the account is not deleted on other AWS error."""
        client_error = ClientError(
            error_response={'Error': {'Code': 'OtherException'}},
            operation_name=Mock(),
        )

        with patch.object(models, 'disable_cloudtrail') as mock_cloudtrail,\
                patch.object(sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error
            with self.assertRaises(CloudTrailCannotStopLogging):
                self.account.delete()

        self.assertEqual(1, models.AwsCloudAccount.objects.count())

    def test_delete_succeeds_when_cloudtrial_does_not_exist(self):
        """Test that an account is deleted if cloudtrail does not exist."""
        client_error = ClientError(
            error_response={'Error': {'Code': 'TrailNotFoundException'}},
            operation_name=Mock(),
        )

        with patch.object(models, 'disable_cloudtrail') as mock_cloudtrail,\
                patch.object(sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error

            self.account.delete()

        self.assertEqual(0, models.AwsCloudAccount.objects.count())

    def test_delete_succeeds_when_aws_account_cannot_be_accessed(self):
        """Test that an account is deleted if AWS account can't be accessed."""
        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDenied'}},
            operation_name=Mock(),
        )

        with patch.object(models, 'disable_cloudtrail') as mock_cloudtrail,\
                patch.object(sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error

            self.account.delete()

        self.assertEqual(0, models.AwsCloudAccount.objects.count())

    def test_delete_cleans_up_instance_events_run(self):
        """Test that deleting an account cleans up instances/events/runs."""
        instance = helper.generate_aws_instance(cloud_account=self.account)
        runtime = (
            util_helper.utc_dt(2019, 1, 1, 0, 0, 0),
            util_helper.utc_dt(2019, 1, 2, 0, 0, 0)
        )

        helper.generate_single_run(instance=instance, runtime=runtime)

        with patch.object(models, 'disable_cloudtrail'),\
                patch.object(sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            self.account.delete()

        self.assertEqual(0, models.AwsCloudAccount.objects.count())
        self.assertEqual(0, models.AwsInstanceEvent.objects.count())
        self.assertEqual(0, models.InstanceEvent.objects.count())
        self.assertEqual(0, models.Run.objects.count())
        self.assertEqual(0, models.AwsInstance.objects.count())
        self.assertEqual(0, models.Instance.objects.count())


class InstanceModelTest(TestCase):
    """Instance Model Test Cases."""

    def setUp(self):
        """Set up basic aws account."""
        self.account = helper.generate_aws_account()

        self.image = helper.generate_aws_image()
        self.instance = helper.generate_aws_instance(
            cloud_account=self.account,
            image=self.image
        )

    def test_delete_instance_cleans_up_machineimage(self):
        """Test that deleting an instance cleans up its associated image."""
        self.instance.delete()
        self.assertEqual(0, models.AwsMachineImage.objects.count())
        self.assertEqual(0, models.MachineImage.objects.count())

    def test_delete_instance_does_not_clean_up_shared_machineimage(self):
        """Test that deleting an instance does not clean up an shared image."""
        helper.generate_aws_instance(
            cloud_account=self.account,
            image=self.image
        )
        self.instance.delete()

        self.assertEqual(1, models.AwsMachineImage.objects.count())
        self.assertEqual(1, models.MachineImage.objects.count())
