"""Collection of tests for tasks.verify_verify_tasks."""

from django.test import TestCase
from django_celery_beat.models import PeriodicTask

from api.clouds.aws.models import AwsCloudAccount
from api.clouds.aws.tasks import verify_verify_tasks
from api.tests import helper as account_helper


class VerifyVerifyAccountPeriodicTaskTest(TestCase):
    """Task 'verify_verify_tasks' test cases."""

    def test_noop(self):
        """No tasks need creation or cleaning up."""
        account_helper.generate_aws_account(generate_verify_task=True)

        aws_clount_before_count = AwsCloudAccount.objects.filter(
            verify_task_id__isnull=False
        ).count()
        verify_task_before_count = PeriodicTask.objects.filter(
            task="api.clouds.aws.tasks.verify_account_permissions"
        ).count()

        verify_verify_tasks()

        self.assertEqual(
            aws_clount_before_count,
            AwsCloudAccount.objects.filter(verify_task_id__isnull=False).count(),
        )
        self.assertEqual(
            verify_task_before_count,
            PeriodicTask.objects.filter(
                task="api.clouds.aws.tasks.verify_account_permissions"
            ).count(),
        )

    def test_orphaned_tasks(self):
        """Orphaned verify tasks get cleaned up."""
        PeriodicTask.objects.create(
            task="api.clouds.aws.tasks.verify_account_permissions"
        )

        self.assertEqual(AwsCloudAccount.objects.all().count(), 0)
        self.assertEqual(
            PeriodicTask.objects.filter(
                task="api.clouds.aws.tasks.verify_account_permissions"
            ).count(),
            1,
        )

        with self.assertLogs("api.clouds.aws.tasks", level="INFO") as cm:
            verify_verify_tasks()

            self.assertEqual(len(cm.records), 1)
            self.assertEqual(cm.records[0].levelname, "ERROR")
            self.assertIn("Found orphaned verify task", cm.records[0].message)

        self.assertEqual(AwsCloudAccount.objects.all().count(), 0)
        self.assertEqual(
            PeriodicTask.objects.filter(
                task="api.clouds.aws.tasks.verify_account_permissions"
            ).count(),
            0,
        )

    def test_enabled_task_missing(self):
        """Enabled clounts get a task."""
        account_helper.generate_aws_account(generate_verify_task=False)

        self.assertEqual(AwsCloudAccount.objects.all().count(), 1)
        self.assertEqual(
            PeriodicTask.objects.filter(
                task="api.clouds.aws.tasks.verify_account_permissions"
            ).count(),
            0,
        )

        with self.assertLogs("api.clouds.aws.tasks", level="INFO") as cm:
            verify_verify_tasks()

            self.assertEqual(len(cm.records), 1)
            self.assertEqual(cm.records[0].levelname, "ERROR")
            self.assertIn(
                "enabled, but missing verification task. Creating.",
                cm.records[0].message,
            )

        self.assertEqual(AwsCloudAccount.objects.all().count(), 1)
        self.assertEqual(
            PeriodicTask.objects.filter(
                task="api.clouds.aws.tasks.verify_account_permissions"
            ).count(),
            1,
        )
        self.assertEqual(
            AwsCloudAccount.objects.all().first().verify_task_id,
            PeriodicTask.objects.filter(
                task="api.clouds.aws.tasks.verify_account_permissions"
            )
            .first()
            .id,
        )
