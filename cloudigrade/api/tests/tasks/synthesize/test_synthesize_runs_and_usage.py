"""Collection of tests for api.tasks.synthesize.synthesize_runs_and_usage."""

from django.test import TestCase, override_settings

from api import AWS_PROVIDER_STRING, CLOUD_PROVIDERS, models
from api.tasks import synthesize
from api.tests.tasks.synthesize import create_synthetic_data_request_without_post_save


class SynthesizeInstanceEventsTest(TestCase):
    """api.tasks.synthesize_runs_and_usage test case."""

    def test_synthesize_runs_and_usage(self):
        """
        Test happy path to create Runs and ConcurrentUsage for the SyntheticDataRequest.

        We expect each user (one for each CLOUD_PROVIDERS) to have "since_days_ago + 2"
        days of concurrent usage calculations because synthesized runs start at
        "today - since_days_ago", and we calculate usage starting one day older than
        the runs start through "today".

        This test need CELERY_TASK_ALWAYS_EAGER=True because synthesize_runs_and_usage
        makes use of several other async tasks that must complete to see results.
        """
        since_days_ago = 10
        expected_concurrent_usage_count = since_days_ago + 2
        for cloud_type in CLOUD_PROVIDERS:
            request = create_synthetic_data_request_without_post_save(
                cloud_type=cloud_type,
                create_kwargs={
                    "since_days_ago": since_days_ago,
                    "image_rhel_chance": 1.0,
                },
            )
            with override_settings(CELERY_TASK_ALWAYS_EAGER=True):
                response = synthesize.synthesize_runs_and_usage(request.id)
            self.assertEqual(response, request.id)
            self.assertEqual(
                expected_concurrent_usage_count,
                models.ConcurrentUsage.objects.filter(user=request.user).count(),
            )
            # Assert *at least* one of them has actual RHEL usage.
            # We don't attempt to discern the exact count because of randomness.
            self.assertTrue(
                models.ConcurrentUsage.objects.filter(user=request.user)
                .exclude(maximum_counts="[]")
                .exists(),
            )

    def test_synthesize_runs_and_usage_but_no_cloud_account(self):
        """Test early return if the SyntheticDataRequest has no CloudAccount."""
        request = create_synthetic_data_request_without_post_save(
            cloud_type=AWS_PROVIDER_STRING, synthesize_cloud_accounts=False
        )
        response = synthesize.synthesize_runs_and_usage(request.id)
        self.assertIsNone(response)
        self.assertFalse(models.Run.objects.exists())
        self.assertFalse(models.ConcurrentUsage.objects.exists())

    def test_synthesize_runs_and_usage_but_request_id_not_found(self):
        """Test early return if the SyntheticDataRequest does not exist."""
        self.assertFalse(models.SyntheticDataRequest.objects.exists())
        response = synthesize.synthesize_runs_and_usage(1)
        self.assertIsNone(response)
        self.assertFalse(models.Run.objects.exists())
        self.assertFalse(models.ConcurrentUsage.objects.exists())
