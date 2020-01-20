"""Collection of tests for custom Django model logic."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.test import TestCase, TransactionTestCase

import api.clouds.aws.util
from api import models
from api.clouds.aws import models as aws_models
from api.tests import helper
from util.aws import sts
from util.exceptions import CloudTrailCannotStopLogging
from util.tests import helper as util_helper


class AwsCloudAccountModelTest(TransactionTestCase):
    """AwsCloudAccount Model Test Cases."""

    def setUp(self):
        """Set up basic aws account."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        self.role = util_helper.generate_dummy_role()
        self.account = helper.generate_aws_account(
            aws_account_id=aws_account_id, arn=arn, name="test"
        )

    def test_cloud_account_str(self):
        """Test that the CloudAccount str (and repr) is valid."""
        mock_logger = Mock()
        mock_logger.info(str(self.account))
        info_calls = mock_logger.info.mock_calls
        message = info_calls[0][1][0]
        self.assertTrue(message.startswith("CloudAccount("))

    def test_aws_cloud_account_str(self):
        """Test that the AwsCloudAccount str (and repr) is valid."""
        mock_logger = Mock()
        mock_logger.info(str(self.account.content_object))
        info_calls = mock_logger.info.mock_calls
        message = info_calls[0][1][0]
        self.assertTrue(message.startswith("AwsCloudAccount("))

    def test_delete_succeeds(self):
        """Test that an account is deleted if there are no errors."""
        with patch.object(sts, "boto3") as mock_boto3, patch.object(
            aws_models, "disable_cloudtrail"
        ):
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            self.account.delete()
            self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    def test_delete_succeeds_on_access_denied_exception(self):
        """Test that the account is deleted on CloudTrail access denied."""
        client_error = ClientError(
            error_response={"Error": {"Code": "AccessDeniedException"}},
            operation_name=Mock(),
        )

        with patch.object(
            aws_models, "disable_cloudtrail"
        ) as mock_cloudtrail, patch.object(sts, "boto3") as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error

            self.account.delete()

        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    def test_delete_fails_on_other_cloudtrail_exception(self):
        """Test that the account is not deleted on other AWS error."""
        client_error = ClientError(
            error_response={"Error": {"Code": "OtherException"}}, operation_name=Mock(),
        )
        with patch.object(
            aws_models, "disable_cloudtrail"
        ) as mock_cloudtrail, patch.object(sts, "boto3") as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error
            with self.assertRaises(CloudTrailCannotStopLogging):
                self.account.delete()

        self.assertEqual(1, aws_models.AwsCloudAccount.objects.count())

    def test_delete_succeeds_when_cloudtrial_does_not_exist(self):
        """Test that an account is deleted if cloudtrail does not exist."""
        client_error = ClientError(
            error_response={"Error": {"Code": "TrailNotFoundException"}},
            operation_name=Mock(),
        )

        with patch.object(
            aws_models, "disable_cloudtrail"
        ) as mock_cloudtrail, patch.object(sts, "boto3") as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error

            self.account.delete()

        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    def test_delete_succeeds_when_aws_account_cannot_be_accessed(self):
        """Test that an account is deleted if AWS account can't be accessed."""
        client_error = ClientError(
            error_response={"Error": {"Code": "AccessDenied"}}, operation_name=Mock(),
        )

        with patch.object(
            aws_models, "disable_cloudtrail"
        ) as mock_cloudtrail, patch.object(sts, "boto3") as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error

            self.account.delete()

        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    def test_delete_cleans_up_instance_events_run(self):
        """Test that deleting an account cleans up instances/events/runs."""
        instance = helper.generate_aws_instance(cloud_account=self.account)
        runtime = (
            util_helper.utc_dt(2019, 1, 1, 0, 0, 0),
            util_helper.utc_dt(2019, 1, 2, 0, 0, 0),
        )

        helper.generate_single_run(instance=instance, runtime=runtime)

        with patch.object(aws_models, "disable_cloudtrail"), patch.object(
            sts, "boto3"
        ) as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            self.account.delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())
        self.assertEqual(0, models.CloudAccount.objects.count())
        self.assertEqual(0, aws_models.AwsInstanceEvent.objects.count())
        self.assertEqual(0, models.InstanceEvent.objects.count())
        self.assertEqual(0, models.Run.objects.count())
        self.assertEqual(0, aws_models.AwsInstance.objects.count())
        self.assertEqual(0, models.Instance.objects.count())

    def test_delete_via_queryset_succeeds_on_known_exception(self):
        """Account is deleted via queryset if a known exception occurs."""
        client_error = ClientError(
            error_response={"Error": {"Code": "AccessDenied"}}, operation_name=Mock(),
        )
        with patch.object(
            aws_models, "disable_cloudtrail"
        ) as mock_cloudtrail, patch.object(sts, "boto3") as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error
            aws_models.AwsCloudAccount.objects.all().delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    def test_delete_via_queryset_fails_on_other_exception(self):
        """Account is not deleted via queryset on unexpected AWS error."""
        client_error = ClientError(
            error_response={"Error": {"Code": "OtherException"}}, operation_name=Mock(),
        )
        with patch.object(
            aws_models, "disable_cloudtrail"
        ) as mock_cloudtrail, patch.object(sts, "boto3") as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error
            with self.assertRaises(CloudTrailCannotStopLogging):
                aws_models.AwsCloudAccount.objects.all().delete()
        self.assertEqual(1, aws_models.AwsCloudAccount.objects.count())

    def test_delete_via_queryset_cleans_up_instance_events_run(self):
        """Deleting an account via queryset cleans up instances/events/runs."""
        instance = helper.generate_aws_instance(cloud_account=self.account)
        runtime = (
            util_helper.utc_dt(2019, 1, 1, 0, 0, 0),
            util_helper.utc_dt(2019, 1, 2, 0, 0, 0),
        )
        helper.generate_single_run(instance=instance, runtime=runtime)
        with patch.object(aws_models, "disable_cloudtrail"), patch.object(
            sts, "boto3"
        ) as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            aws_models.AwsCloudAccount.objects.all().delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())
        self.assertEqual(0, models.CloudAccount.objects.count())
        self.assertEqual(0, aws_models.AwsInstanceEvent.objects.count())
        self.assertEqual(0, models.InstanceEvent.objects.count())
        self.assertEqual(0, models.Run.objects.count())
        self.assertEqual(0, aws_models.AwsInstance.objects.count())
        self.assertEqual(0, models.Instance.objects.count())


class InstanceModelTest(TestCase):
    """Instance Model Test Cases."""

    def setUp(self):
        """Set up basic aws account."""
        self.account = helper.generate_aws_account()

        self.image = helper.generate_aws_image()
        self.instance = helper.generate_aws_instance(
            cloud_account=self.account, image=self.image
        )
        self.instance_without_image = helper.generate_aws_instance(
            cloud_account=self.account, no_image=True,
        )

    def test_instance_str(self):
        """Test that the Instance str (and repr) is valid."""
        mock_logger = Mock()
        mock_logger.info(str(self.instance))
        info_calls = mock_logger.info.mock_calls
        message = info_calls[0][1][0]
        self.assertTrue(message.startswith("Instance("))

    def test_aws_instance_str(self):
        """Test that the AwsInstance str (and repr) is valid."""
        mock_logger = Mock()
        mock_logger.info(str(self.instance.content_object))
        info_calls = mock_logger.info.mock_calls
        message = info_calls[0][1][0]
        self.assertTrue(message.startswith("AwsInstance("))

    def test_delete_instance_cleans_up_machineimage(self):
        """Test that deleting an instance cleans up its associated image."""
        self.instance.delete()
        self.instance_without_image.delete()
        self.assertEqual(0, aws_models.AwsMachineImage.objects.count())
        self.assertEqual(0, models.MachineImage.objects.count())

    def test_delete_instance_does_not_clean_up_shared_machineimage(self):
        """Test that deleting an instance does not clean up an shared image."""
        helper.generate_aws_instance(cloud_account=self.account, image=self.image)
        self.instance.delete()
        self.instance_without_image.delete()

        self.assertEqual(1, aws_models.AwsMachineImage.objects.count())
        self.assertEqual(1, models.MachineImage.objects.count())

    def test_delete_instance_from_queryset_cleans_up_machineimage(self):
        """Test that deleting instances via queryset cleans up its images."""
        aws_models.AwsInstance.objects.all().delete()
        self.assertEqual(0, aws_models.AwsMachineImage.objects.count())
        self.assertEqual(0, models.MachineImage.objects.count())
        self.assertEqual(0, aws_models.AwsInstance.objects.count())
        self.assertEqual(0, models.Instance.objects.count())

    def test_delete_multiple_instance_from_queryset_cleans_up_image(self):
        """Deleting instances that share an image cleans up the image."""
        helper.generate_aws_instance(cloud_account=self.account, image=self.image)
        aws_models.AwsInstance.objects.all().delete()
        self.assertEqual(0, aws_models.AwsMachineImage.objects.count())
        self.assertEqual(0, models.MachineImage.objects.count())
        self.assertEqual(0, aws_models.AwsInstance.objects.count())
        self.assertEqual(0, models.Instance.objects.count())


class MachineImageModelTest(TestCase):
    """Instance Model Test Cases."""

    def setUp(self):
        """Set up basic image objects."""
        self.machine_image = helper.generate_aws_image()
        copy_ec2_ami_id = util_helper.generate_dummy_image_id()
        api.clouds.aws.util.create_aws_machine_image_copy(
            copy_ec2_ami_id, self.machine_image.content_object.ec2_ami_id
        )
        self.aws_machine_image_copy = aws_models.AwsMachineImageCopy.objects.get(
            reference_awsmachineimage=self.machine_image.content_object
        )

    def test_machine_image_str(self):
        """Test that the MachineImage str (and repr) is valid."""
        mock_logger = Mock()
        mock_logger.info(str(self.machine_image))
        info_calls = mock_logger.info.mock_calls
        message = info_calls[0][1][0]
        self.assertTrue(message.startswith("MachineImage("))

    def test_aws_machine_image_str(self):
        """Test that the AwsMachineImage str (and repr) is valid."""
        mock_logger = Mock()
        mock_logger.info(str(self.machine_image.content_object))
        info_calls = mock_logger.info.mock_calls
        message = info_calls[0][1][0]
        self.assertTrue(message.startswith("AwsMachineImage("))

    def test_aws_machine_image_copy_str(self):
        """Test that the AwsMachineImageCopy str (and repr) is valid."""
        mock_logger = Mock()
        mock_logger.info(str(self.aws_machine_image_copy))
        info_calls = mock_logger.info.mock_calls
        message = info_calls[0][1][0]
        self.assertTrue(message.startswith("AwsMachineImageCopy("))


class RunModelTest(TransactionTestCase):
    """Run Model Test Cases."""

    def test_delete_run_removes_concurrent_usage(self):
        """Test when a run is deleted, related concurrent usage are deleted."""
        account = helper.generate_aws_account()

        image = helper.generate_aws_image()
        instance = helper.generate_aws_instance(cloud_account=account, image=image)
        runtime = (
            util_helper.utc_dt(2019, 1, 1, 0, 0, 0),
            util_helper.utc_dt(2019, 1, 2, 0, 0, 0),
        )
        helper.generate_single_run(instance=instance, runtime=runtime)
        self.assertGreater(models.ConcurrentUsage.objects.count(), 0)
        models.Run.objects.all().delete()
        self.assertEqual(models.ConcurrentUsage.objects.count(), 0)
