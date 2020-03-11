"""Collection of tests for custom Django model logic."""
from random import choice
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase, TransactionTestCase

import api.clouds.aws.util
from api import models
from api.clouds.aws import models as aws_models
from api.tests import helper
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
        with patch("api.clouds.aws.util.disable_cloudtrail") as mock_disable_cloudtrail:
            mock_disable_cloudtrail.return_value = True
            self.account.delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    def test_delete_succeeds_if_disable_cloudtrail_fails(self):
        """Test that the account is deleted even if the CloudTrail is not disabled."""
        with patch("api.clouds.aws.util.disable_cloudtrail") as mock_disable_cloudtrail:
            mock_disable_cloudtrail.return_value = False
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

        with patch("api.clouds.aws.util.disable_cloudtrail") as mock_disable_cloudtrail:
            mock_disable_cloudtrail.return_value = True
            self.account.delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())
        self.assertEqual(0, models.CloudAccount.objects.count())
        self.assertEqual(0, aws_models.AwsInstanceEvent.objects.count())
        self.assertEqual(0, models.InstanceEvent.objects.count())
        self.assertEqual(0, models.Run.objects.count())
        self.assertEqual(0, aws_models.AwsInstance.objects.count())
        self.assertEqual(0, models.Instance.objects.count())

    def test_delete_via_queryset_succeeds_if_disable_cloudtrail_fails(self):
        """Account is deleted via queryset even if the CloudTrail is not disabled."""
        with patch("api.clouds.aws.util.disable_cloudtrail") as mock_disable_cloudtrail:
            mock_disable_cloudtrail.return_value = False
            aws_models.AwsCloudAccount.objects.all().delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    def test_delete_via_queryset_cleans_up_instance_events_run(self):
        """Deleting an account via queryset cleans up instances/events/runs."""
        instance = helper.generate_aws_instance(cloud_account=self.account)
        runtime = (
            util_helper.utc_dt(2019, 1, 1, 0, 0, 0),
            util_helper.utc_dt(2019, 1, 2, 0, 0, 0),
        )
        helper.generate_single_run(instance=instance, runtime=runtime)
        with patch("api.clouds.aws.util.disable_cloudtrail") as mock_disable_cloudtrail:
            mock_disable_cloudtrail.return_value = True
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

    def test_is_marketplace_name_check(self):
        """Test that is_marketplace is True if image name and owner matches."""
        machine_image = helper.generate_aws_image(
            name="marketplace-hourly2",
            owner_aws_account_id=choice(settings.RHEL_IMAGES_AWS_ACCOUNTS),
        )
        self.assertTrue(machine_image.content_object.is_marketplace)

    def test_is_marketplace_true_if_aws_marketplace_image(self):
        """Test that the AwsMachineImageCopy str (and repr) is valid."""
        aws_machine_image = helper.generate_aws_image().content_object
        aws_machine_image.aws_marketplace_image = True
        aws_machine_image.save()
        self.assertTrue(aws_machine_image.is_marketplace)


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
