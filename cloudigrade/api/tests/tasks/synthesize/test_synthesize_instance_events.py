"""Collection of tests for api.tasks.synthesize.synthesize_instance_events."""

from django.test import TestCase

from api import AWS_PROVIDER_STRING, CLOUD_PROVIDERS, models
from api.tasks import synthesize
from api.tests.tasks.synthesize import create_synthetic_data_request_without_post_save


class SynthesizeInstanceEventsTest(TestCase):
    """api.tasks.synthesize_instance_events test case."""

    def test_synthesize_instance_events(self):
        """
        Test happy path to create InstanceEvents for the SyntheticDataRequest.

        We expect requests for all CLOUD_PROVIDERS to have non-zero counts of their
        respective InstanceEvent types to be created successfully.
        """
        for cloud_type in CLOUD_PROVIDERS:
            request = create_synthetic_data_request_without_post_save(
                cloud_type=cloud_type, synthesize_instance_events=False
            )
            response = synthesize.synthesize_instance_events(request.id)
            self.assertEqual(response, request.id)
            request.refresh_from_db()
            for instance in models.Instance.objects.filter(
                cloud_account__user__syntheticdatarequest=request
            ):
                self.assertTrue(
                    models.InstanceEvent.objects.filter(instance=instance).exists()
                )

    def test_synthesize_instance_events_but_no_instances(self):
        """Test early return if the SyntheticDataRequest has no Instance."""
        request = create_synthetic_data_request_without_post_save(
            cloud_type=AWS_PROVIDER_STRING, synthesize_instances=False
        )
        response = synthesize.synthesize_instance_events(request.id)
        self.assertIsNone(response)
        self.assertFalse(models.InstanceEvent.objects.exists())

    def test_synthesize_instance_events_but_request_id_not_found(self):
        """Test early return if the SyntheticDataRequest does not exist."""
        self.assertFalse(models.SyntheticDataRequest.objects.exists())
        response = synthesize.synthesize_instance_events(1)
        self.assertIsNone(response)
        self.assertFalse(models.InstanceEvent.objects.exists())

    def test_synthesize_instance_events_none_when_requesting_zero(self):
        """
        Test no InstanceEvents are created when requested min and mean counts are 0.

        We expect requests for all CLOUD_PROVIDERS to have non-zero counts of their
        respective InstanceEvent types to be created successfully.
        """
        request = create_synthetic_data_request_without_post_save(
            cloud_type=AWS_PROVIDER_STRING,
            create_kwargs={
                "run_count_per_instance_min": 0,
                "run_count_per_instance_mean": 0,
            },
            synthesize_instance_events=False,
        )
        response = synthesize.synthesize_instance_events(request.id)
        self.assertEqual(response, request.id)
        request.refresh_from_db()
        self.assertEqual(request.instance_count, models.Instance.objects.count())
        self.assertEqual(0, models.InstanceEvent.objects.count())
