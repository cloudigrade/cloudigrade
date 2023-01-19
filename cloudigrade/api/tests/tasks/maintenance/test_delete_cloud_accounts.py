"""Collection of tests for tasks.maintenance._delete_cloud_accounts helper function."""

from django.test import TestCase, override_settings

from api import models
from api.clouds.aws import models as aws_models
from api.tasks import maintenance
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class DeleteCloudAccountsTest(TestCase):
    """tasks._delete_cloud_accounts test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user = util_helper.generate_test_user()

        # Set up two AWS accounts, each with two instances
        # There will be three total images, one of which is used by an instance in each
        # separate AWS account.
        self.account_aws_1 = api_helper.generate_cloud_account_aws(user=self.user)
        self.account_aws_2 = api_helper.generate_cloud_account_aws(user=self.user)
        self.image_aws_shared = api_helper.generate_image()
        self.instance_aws_1_1 = api_helper.generate_instance(self.account_aws_1)
        self.instance_aws_1_2 = api_helper.generate_instance(
            self.account_aws_1, image=self.image_aws_shared
        )
        self.instance_aws_2_1 = api_helper.generate_instance(self.account_aws_2)
        self.instance_aws_2_2 = api_helper.generate_instance(
            self.account_aws_2, image=self.image_aws_shared
        )

        # Set up two Azure accounts, each with two instances.
        # There will be three total images, one of which is used by an instance in each
        # separate Azure account.
        self.account_azure_1 = api_helper.generate_cloud_account_azure(user=self.user)
        self.account_azure_2 = api_helper.generate_cloud_account_azure(user=self.user)
        self.image_azure_shared = api_helper.generate_image(
            cloud_type=api_helper.AWS_PROVIDER_STRING
        )
        self.instance_azure_1_1 = api_helper.generate_instance(self.account_azure_1)
        self.instance_azure_1_2 = api_helper.generate_instance(
            self.account_azure_1, image=self.image_azure_shared
        )
        self.instance_azure_2_1 = api_helper.generate_instance(self.account_azure_2)
        self.instance_azure_2_2 = api_helper.generate_instance(
            self.account_azure_2, image=self.image_azure_shared
        )

    def generate_activity(self):
        """
        Generate activity for all the test instances.

        Simply have all generated instances start and stop at same times. We don't care
        about randomness of timing in these tests, just that things do or don't exist.
        """
        start_time = util_helper.utc_dt(2021, 8, 9, 1, 2, 3)
        stop_time = util_helper.utc_dt(2021, 8, 10, 4, 5, 6)
        powered_times = ((start_time, stop_time),)
        api_helper.generate_instance_events(self.instance_aws_1_1, powered_times)
        api_helper.generate_instance_events(self.instance_aws_1_2, powered_times)
        api_helper.generate_instance_events(self.instance_aws_2_1, powered_times)
        api_helper.generate_instance_events(self.instance_aws_2_2, powered_times)
        api_helper.generate_instance_events(self.instance_azure_1_1, powered_times)
        api_helper.generate_instance_events(self.instance_azure_1_2, powered_times)
        api_helper.generate_instance_events(self.instance_azure_2_1, powered_times)
        api_helper.generate_instance_events(self.instance_azure_2_2, powered_times)

    def assertObjectCountsBeforeDelete(self):
        """Sanity-check expected object counts before deleting."""
        self.assertEqual(models.CloudAccount.objects.count(), 4)
        self.assertEqual(models.Instance.objects.count(), 8)
        self.assertEqual(models.Run.objects.count(), 0)
        self.assertEqual(models.ConcurrentUsage.objects.count(), 0)
        self.assertEqual(models.MachineImage.objects.count(), 6)

    def assertObjectCountsAfterDelete(self, accounts_deleted=1):
        """Sanity-check expected object counts before deleting."""
        self.assertEqual(models.CloudAccount.objects.count(), 4 - accounts_deleted)
        self.assertEqual(models.Instance.objects.count(), 2 * (4 - accounts_deleted))
        # Deleting an account's Instances should also delete the related Runs, and that
        # should also result in deleting the related ConcurrentUsages.
        self.assertEqual(models.Run.objects.count(), 0)
        self.assertEqual(models.ConcurrentUsage.objects.count(), 0)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_cloud_accounts_single_aws(self):
        """
        Test deleting one AWS account should not affect other accounts.

        The image that was used by instances in both AWS accounts should still exist.
        """
        self.generate_activity()
        self.assertObjectCountsBeforeDelete()

        maintenance.delete_cloud_account(self.account_aws_1.id)

        self.assertObjectCountsAfterDelete()
        # The deleted account should not exist, but the other should be okay.
        with self.assertRaises(models.CloudAccount.DoesNotExist):
            self.account_aws_1.refresh_from_db()
        self.account_aws_2.refresh_from_db()
        self.account_azure_1.refresh_from_db()
        self.account_azure_2.refresh_from_db()

        # The shared image should exist since it's used by the other AWS account.
        self.image_aws_shared.refresh_from_db()

        # So, we should have 5 images: 3 Azure images, 1 AWS image that was shared by
        # the two AWS accounts, and 1 image was used only by the other AWS account.
        self.assertEqual(models.MachineImage.objects.count(), 5)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_cloud_accounts_single_azure(self):
        """
        Test deleting one Azure account should not affect other accounts.

        The image that was used by instances in both Azure accounts should still exist.
        """
        self.generate_activity()
        self.assertObjectCountsBeforeDelete()

        maintenance.delete_cloud_account(self.account_azure_1.id)

        self.assertObjectCountsAfterDelete()
        # The deleted account should not exist, but the other should be okay.
        with self.assertRaises(models.CloudAccount.DoesNotExist):
            self.account_azure_1.refresh_from_db()
        self.account_azure_2.refresh_from_db()
        self.account_aws_1.refresh_from_db()
        self.account_aws_2.refresh_from_db()

        # The shared image should exist since it's used by the other Azure account.
        self.image_azure_shared.refresh_from_db()

        # So, we should have 5 images: 3 AWS images, 1 Azure image that was shared by
        # the two Azure accounts, and 1 image was used only by the other Azure account.
        self.assertEqual(models.MachineImage.objects.count(), 5)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_cloud_accounts_both_aws(self):
        """Test deleting both AWS accounts also deletes the shared image."""
        self.generate_activity()
        self.assertObjectCountsBeforeDelete()

        maintenance.delete_cloud_account(self.account_aws_1.id)
        maintenance.delete_cloud_account(self.account_aws_2.id)

        self.assertObjectCountsAfterDelete(accounts_deleted=2)
        with self.assertRaises(models.CloudAccount.DoesNotExist):
            self.account_aws_1.refresh_from_db()
        with self.assertRaises(models.CloudAccount.DoesNotExist):
            self.account_aws_2.refresh_from_db()
        self.account_azure_1.refresh_from_db()
        self.account_azure_2.refresh_from_db()

        # The shared AWS image should be gone since nothing uses it now.
        with self.assertRaises(models.MachineImage.DoesNotExist):
            self.image_aws_shared.refresh_from_db()

        # So, we should have only the 3 Azure images.
        self.assertEqual(models.MachineImage.objects.count(), 3)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_when_missing_cloud_account_content_object(self):
        """Test partial delete when cloud_account.content_object is None."""
        self.generate_activity()
        self.assertObjectCountsBeforeDelete()

        # Delete only the related AwsCloudAccount to simulate weird conditions.
        # It's unclear how that could happen unless we have a hidden race condition
        # related to the delete process while processing multiple messages in parallel.
        aws_cloud_accounts = aws_models.AwsCloudAccount.objects.filter(
            id=self.account_aws_1.object_id
        )
        aws_cloud_accounts._raw_delete(aws_cloud_accounts.db)

        # verify the related CloudAccount is still present after the raw_delete above
        self.account_aws_1.refresh_from_db()

        with self.assertLogs(
            "api.tasks.maintenance", level="INFO"
        ) as logs_maintenance, self.assertLogs(
            "api.models", level="INFO"
        ) as logs_models:
            maintenance.delete_cloud_account(self.account_aws_1.id)

        self.assertObjectCountsAfterDelete()
        maintenance_infos = [
            r.getMessage() for r in logs_maintenance.records if r.levelname == "INFO"
        ]
        maintenance_errors = [
            r.getMessage() for r in logs_maintenance.records if r.levelname == "ERROR"
        ]
        model_errors = [
            r.getMessage() for r in logs_models.records if r.levelname == "ERROR"
        ]
        self.assertEqual(len(maintenance_infos), 1)
        self.assertEqual(len(maintenance_errors), 1)
        self.assertEqual(len(model_errors), 1)
        self.assertIn("Deleting CloudAccount with ID", maintenance_infos[0])
        self.assertIn("cloud_account.content_object is None", maintenance_errors[0])
        self.assertIn("content_object is missing", model_errors[0])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_delete_when_missing_multiple_related_objects(self):
        """Test partial delete when multiple related content_objects are None."""
        self.generate_activity()
        self.assertObjectCountsBeforeDelete()

        # Delete only the related AwsCloudAccount to simulate weird conditions.
        # Also delete the related AwsInstanceEvents and AwsInstances.
        # It's unclear how that could happen unless we have a hidden race condition
        # related to the delete process while processing multiple messages in parallel.
        aws_cloud_accounts = aws_models.AwsCloudAccount.objects.filter(
            id=self.account_aws_1.object_id
        )
        aws_cloud_accounts._raw_delete(aws_cloud_accounts.db)
        aws_instance_events = aws_models.AwsInstanceEvent.objects.filter(
            instance_event__instance__cloud_account_id=self.account_aws_1.object_id
        )
        aws_instance_events._raw_delete(aws_instance_events.db)
        aws_instances = aws_models.AwsInstance.objects.filter(
            instance__cloud_account_id=self.account_aws_1.object_id
        )
        aws_instances._raw_delete(aws_instances.db)

        with self.assertLogs("api.tasks.maintenance", level="INFO") as logs_maintenance:
            maintenance.delete_cloud_account(self.account_aws_1.id)

        self.assertObjectCountsAfterDelete()
        maintenance_infos = [
            r.getMessage() for r in logs_maintenance.records if r.levelname == "INFO"
        ]
        maintenance_errors = [
            r.getMessage() for r in logs_maintenance.records if r.levelname == "ERROR"
        ]
        self.assertEqual(len(maintenance_infos), 3)
        self.assertEqual(len(maintenance_errors), 1)
        self.assertIn("Deleting CloudAccount with ID", maintenance_infos[0])
        self.assertIn(
            "Could not delete cloud-specific InstanceEvent class",
            maintenance_infos[1],
        )
        self.assertIn(
            "Could not delete cloud-specific Instance class",
            maintenance_infos[2],
        )
        self.assertIn("cloud_account.content_object is None", maintenance_errors[0])
