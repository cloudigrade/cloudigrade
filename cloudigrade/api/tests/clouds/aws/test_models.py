"""Collection of tests for custom Django model logic."""
import json
import logging
from random import choice
from unittest.mock import patch

from django.conf import settings
from django.db.models import ForeignKey
from django.test import TestCase, TransactionTestCase
from django_celery_beat.models import IntervalSchedule, PeriodicTask

import api.clouds.aws.util
from api import models
from api.clouds.aws import models as aws_models
from api.tests import helper
from util.tests import helper as util_helper

logger = logging.getLogger(__name__)


class ModelStrTestMixin:
    """Mixin for test classes to add common assertion for str correctness."""

    def assertTypicalStrOutput(self, instance, exclude_field_names=None):
        """
        Assert instance's str output includes all relevant data.

        Our typical model string representation should look like:
            ClassName(field="value", other_field="value", related_model_id=1)
        """
        if exclude_field_names is None:
            exclude_field_names = ()
        output = str(instance)
        self.assertEqual(output, repr(instance))
        self.assertTrue(output.startswith(f"{instance.__class__.__name__}("))
        field_names = (
            field.name if not isinstance(field, ForeignKey) else f"{field.name}_id"
            for field in instance.__class__._meta.local_fields
            if field.name not in exclude_field_names
        )
        for field_name in field_names:
            self.assertIn(f"{field_name}=", output)


class AwsCloudAccountModelTest(TransactionTestCase, ModelStrTestMixin):
    """AwsCloudAccount Model Test Cases."""

    def setUp(self):
        """Set up basic aws account."""
        self.created_at = util_helper.utc_dt(2019, 1, 1, 0, 0, 0)
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        self.role = util_helper.generate_dummy_role()
        self.account = helper.generate_aws_account(
            aws_account_id=aws_account_id,
            arn=arn,
            name="test",
            created_at=self.created_at,
        )

    def test_cloud_account_str(self):
        """Test that the CloudAccount str (and repr) is valid."""
        excluded_field_names = {"content_type", "object_id"}
        self.assertTypicalStrOutput(self.account, excluded_field_names)

    def test_aws_cloud_account_str(self):
        """Test that the AwsCloudAccount str (and repr) is valid."""
        self.assertTypicalStrOutput(self.account.content_object)

    @patch("api.models.notify_sources_application_availability")
    def test_enable_succeeds(self, mock_sources_notify):
        """
        Test that enabling an account does all the relevant verification and setup.

        Disabling a CloudAccount having an AwsCloudAccount should:

        - set the CloudAccount.is_enabled to True
        - verify AWS IAM access and permissions
        - delay task to describe instances
        """
        # Normally you shouldn't directly manipulate the is_enabled value,
        # but here we need to force it down to check that it gets set back.
        self.account.is_enabled = False
        self.account.save()
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)

        enable_date = util_helper.utc_dt(2019, 1, 4, 0, 0, 0)
        with patch(
            "api.clouds.aws.util.verify_permissions"
        ) as mock_verify_permissions, patch(
            "api.clouds.aws.tasks.initial_aws_describe_instances"
        ) as mock_initial_aws_describe_instances, util_helper.clouditardis(
            enable_date
        ):
            self.account.enable()
            mock_verify_permissions.assert_called()
            mock_initial_aws_describe_instances.delay.assert_called()

        self.account.refresh_from_db()
        self.assertTrue(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, enable_date)

        self.assertTrue(self.account.content_object.verify_task.enabled)
        self.assertEqual(
            self.account.content_object.verify_task.start_time,
            self.account.content_object.created_at,
        )

    def test_enable_failure(self):
        """Test that enabling an account rolls back if cloud-specific step fails."""
        # Normally you shouldn't directly manipulate the is_enabled value,
        # but here we need to force it down to check that it gets set back.
        self.account.is_enabled = False
        self.account.save()
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, self.account.created_at)

        with patch(
            "api.clouds.aws.util.verify_permissions"
        ) as mock_verify_permissions, patch(
            "api.clouds.aws.tasks.initial_aws_describe_instances"
        ) as mock_initial_aws_describe_instances:
            mock_verify_permissions.side_effect = Exception("Something broke.")
            with self.assertRaises(Exception):
                self.account.enable()
            mock_verify_permissions.assert_called()
            mock_initial_aws_describe_instances.delay.assert_not_called()

        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, self.account.created_at)

    @patch("api.models.notify_sources_application_availability")
    def test_disable_succeeds(self, mock_sources_notify):
        """
        Test that disabling an account does all the relevant cleanup.

        Disabling a CloudAccount having an AwsCloudAccount should:

        - set the CloudAccount.is_enabled to False
        - create a power_off InstanceEvent for any powered-on instances
        - disable the CloudTrail (via AwsCloudAccount.disable)
        """
        self.assertTrue(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, self.account.created_at)
        instance = helper.generate_aws_instance(cloud_account=self.account)
        runtimes = [
            (
                util_helper.utc_dt(2019, 1, 1, 0, 0, 0),
                util_helper.utc_dt(2019, 1, 2, 0, 0, 0),
            ),
            (util_helper.utc_dt(2019, 1, 3, 0, 0, 0), None),
        ]

        disable_date = util_helper.utc_dt(2019, 1, 4, 0, 0, 0)
        with util_helper.clouditardis(disable_date):
            # We need to generate the runs while inside the clouditardis because we
            # don't need an ever-growing number of daily ConcurrentUsage objects being
            # created as the real-world clock ticks forward.
            for runtime in runtimes:
                helper.generate_single_run(instance=instance, runtime=runtime)
            self.assertEqual(3, aws_models.AwsInstanceEvent.objects.count())
            with patch(
                "api.clouds.aws.util.disable_cloudtrail"
            ) as mock_disable_cloudtrail:
                mock_disable_cloudtrail.return_value = True
                self.account.disable()
                mock_disable_cloudtrail.assert_called()

        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, self.created_at)
        self.assertEqual(4, aws_models.AwsInstanceEvent.objects.count())

        last_event = (
            models.InstanceEvent.objects.filter(instance=instance)
            .order_by("-occurred_at")
            .first()
        )
        self.assertEqual(last_event.event_type, models.InstanceEvent.TYPE.power_off)

    @patch("api.models.notify_sources_application_availability")
    def test_disable_succeeds_if_no_instance_events(self, mock_sources_notify):
        """Test that disabling an account works despite having no instance events."""
        self.assertTrue(self.account.is_enabled)
        helper.generate_aws_instance(cloud_account=self.account)

        with patch("api.clouds.aws.util.disable_cloudtrail") as mock_disable_cloudtrail:
            mock_disable_cloudtrail.return_value = True
            self.account.disable()
            mock_disable_cloudtrail.assert_called()

        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)
        self.assertEqual(0, aws_models.AwsInstanceEvent.objects.count())

    def test_disable_returns_early_if_account_is_enabled(self):
        """Test that AwsCloudAccount.disable returns early if is_enabled."""
        self.assertTrue(self.account.is_enabled)
        helper.generate_aws_instance(cloud_account=self.account)

        with patch("api.clouds.aws.util.disable_cloudtrail") as mock_disable_cloudtrail:
            mock_disable_cloudtrail.return_value = True
            self.account.content_object.disable()
            mock_disable_cloudtrail.assert_not_called()

    @patch("api.models.notify_sources_application_availability")
    def test_delete_succeeds(self, mock_sources_notify):
        """Test that an account is deleted if there are no errors."""
        with patch("api.clouds.aws.util.disable_cloudtrail") as mock_disable_cloudtrail:
            mock_disable_cloudtrail.return_value = True
            self.account.delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    @patch("api.models.notify_sources_application_availability")
    def test_delete_succeeds_if_disable_cloudtrail_fails(self, mock_notify_sources):
        """Test that the account is deleted even if the CloudTrail is not disabled."""
        with patch("api.clouds.aws.util.disable_cloudtrail") as mock_disable_cloudtrail:
            mock_disable_cloudtrail.return_value = False
            self.account.delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    @patch("api.models.notify_sources_application_availability")
    @patch("api.clouds.aws.util.verify_permissions")
    @patch("api.clouds.aws.tasks.initial_aws_describe_instances")
    def test_delete_cleans_up_related_objects(
        self, mock_describe, mock_verify, mock_notify
    ):
        """
        Verify that deleting an AWS account cleans up related objects.

        Deleting the account should also delete instances, events, runs, and the
        periodic verify task related to it.
        """
        instance = helper.generate_aws_instance(cloud_account=self.account)
        runtime = (
            util_helper.utc_dt(2019, 1, 1, 0, 0, 0),
            util_helper.utc_dt(2019, 1, 2, 0, 0, 0),
        )

        self.account.enable()
        helper.generate_single_run(instance=instance, runtime=runtime)

        # First, verify that objects exist *before* deleting the AwsCloudAccount.
        self.assertGreater(aws_models.AwsCloudAccount.objects.count(), 0)
        self.assertGreater(models.CloudAccount.objects.count(), 0)
        self.assertGreater(aws_models.AwsInstanceEvent.objects.count(), 0)
        self.assertGreater(models.InstanceEvent.objects.count(), 0)
        self.assertGreater(models.Run.objects.count(), 0)
        self.assertGreater(aws_models.AwsInstance.objects.count(), 0)
        self.assertGreater(models.Instance.objects.count(), 0)
        self.assertGreater(PeriodicTask.objects.count(), 0)

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
        self.assertEqual(0, PeriodicTask.objects.count())

    @patch("api.models.notify_sources_application_availability")
    def test_delete_via_queryset_succeeds_if_disable_cloudtrail_fails(
        self, mock_notify_sources
    ):
        """Account is deleted via queryset even if the CloudTrail is not disabled."""
        with patch("api.clouds.aws.util.disable_cloudtrail") as mock_disable_cloudtrail:
            mock_disable_cloudtrail.return_value = False
            aws_models.AwsCloudAccount.objects.all().delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    @patch("api.models.notify_sources_application_availability")
    def test_delete_via_queryset_cleans_up_instance_events_run(
        self, mock_notify_sources
    ):
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

    def test_enable_verify_task_created(self):
        """Verify Task is created."""
        aws_clount = self.account.content_object
        self.assertIsNone(aws_clount.verify_task)

        aws_clount._enable_verify_task()

        self.assertIsNotNone(aws_clount.verify_task)
        self.assertTrue(aws_clount.verify_task.enabled)
        self.assertEqual(aws_clount.verify_task.start_time, aws_clount.created_at)

    @patch("api.models.notify_sources_application_availability")
    @patch("api.clouds.aws.util.verify_permissions")
    @patch("api.clouds.aws.tasks.initial_aws_describe_instances")
    def test_enable_verify_task_existing(self, mock_describe, mock_verify, mock_notify):
        """Verify Task is assigned and re-enabled since it already existed."""
        aws_clount = self.account.content_object
        self.assertIsNone(aws_clount.verify_task)

        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=1, period=IntervalSchedule.DAYS
        )
        verify_task = PeriodicTask.objects.create(
            interval=schedule,
            name=f"Verify {aws_clount.account_arn}.",
            task="api.clouds.aws.tasks.verify_account_permissions",
            kwargs=json.dumps({"account_arn": aws_clount.account_arn,}),
            start_time=self.created_at,
        )

        verify_task.enabled = False
        verify_task.save()

        enable_date = util_helper.utc_dt(2019, 1, 4, 0, 0, 0)
        with util_helper.clouditardis(enable_date):
            self.account.enable()

        self.assertIsNotNone(aws_clount.verify_task)

    @patch("api.models.notify_sources_application_availability")
    def test_disable_verify_task_existing(self, mock_sources_notify):
        """Verify Task is disabled."""
        aws_clount = self.account.content_object
        enable_date = util_helper.utc_dt(2019, 1, 4, 0, 0, 0)
        with patch("api.clouds.aws.util.verify_permissions"), patch(
            "api.clouds.aws.tasks.initial_aws_describe_instances"
        ), util_helper.clouditardis(enable_date):
            self.account.enable()

        self.assertTrue(aws_clount.verify_task.enabled)
        self.account.content_object._disable_verify_task()
        self.assertFalse(aws_clount.verify_task.enabled)

    def test_disable_verify_task_fail(self):
        """Verify Task fails to be disabled, since it does not exist."""
        aws_clount = self.account.content_object
        self.assertIsNone(aws_clount.verify_task)
        with self.assertLogs("api.clouds.aws.models", level="ERROR") as cm:
            self.account.content_object._disable_verify_task()
            self.assertIn("ERROR", cm.output[0])


class InstanceModelTest(TestCase, ModelStrTestMixin):
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
        excluded_field_names = ("content_type", "object_id")
        self.assertTypicalStrOutput(self.instance, excluded_field_names)

    def test_aws_instance_str(self):
        """Test that the AwsInstance str (and repr) is valid."""
        self.assertTypicalStrOutput(self.instance.content_object)

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


class MachineImageModelTest(TestCase, ModelStrTestMixin):
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
        excluded_field_names = ("content_type", "object_id", "inspection_json")
        self.assertTypicalStrOutput(self.machine_image, excluded_field_names)

    def test_aws_machine_image_str(self):
        """Test that the AwsMachineImage str (and repr) is valid."""
        self.assertTypicalStrOutput(self.machine_image.content_object)

    def test_aws_machine_image_copy_str(self):
        """Test that the AwsMachineImageCopy str (and repr) is valid."""
        excluded_field_names = {"awsmachineimage_ptr"}
        self.assertTypicalStrOutput(self.aws_machine_image_copy, excluded_field_names)

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
