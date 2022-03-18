"""Collection of tests for api.tasks.synthesize.synthesize_instances."""

from django.test import TestCase

from api import AWS_PROVIDER_STRING, CLOUD_PROVIDERS, models
from api.tasks import synthesize
from api.tests.tasks.synthesize import create_synthetic_data_request_without_post_save


class SynthesizeInstancesTest(TestCase):
    """api.tasks.synthesize_instances test case."""

    def test_synthesize_instances(self):
        """
        Test happy path to create Instances for the SyntheticDataRequest.

        We expect requests for all CLOUD_PROVIDERS to have non-zero counts of their
        respective Instance types to be created successfully.
        """
        expected_total_instance_count = 0
        for cloud_type in CLOUD_PROVIDERS:
            request = create_synthetic_data_request_without_post_save(
                cloud_type=cloud_type, synthesize_instances=False
            )
            expected_total_instance_count += request.instance_count
            response = synthesize.synthesize_instances(request.id)
            self.assertEqual(response, request.id)
            request.refresh_from_db()
            self.assertGreater(request.instance_count, 0)
            self.assertEqual(
                request.instance_count,
                models.Instance.objects.filter(
                    cloud_account__user__syntheticdatarequest=request
                ).count(),
            )
            for image in models.Instance.objects.filter(
                cloud_account__user__syntheticdatarequest=request
            ):
                self.assertEqual(image.cloud_type, request.cloud_type)
        self.assertEqual(expected_total_instance_count, models.Instance.objects.count())

    def test_synthesize_instances_but_no_images(self):
        """Test early return if the SyntheticDataRequest has no MachineImage."""
        request = create_synthetic_data_request_without_post_save(
            cloud_type=AWS_PROVIDER_STRING, synthesize_images=False
        )
        response = synthesize.synthesize_instances(request.id)
        self.assertIsNone(response)
        self.assertFalse(models.MachineImage.objects.exists())

    def test_synthesize_instances_but_no_cloud_account(self):
        """Test early return if the SyntheticDataRequest has no CloudAccount."""
        request = create_synthetic_data_request_without_post_save(
            cloud_type=AWS_PROVIDER_STRING, synthesize_cloud_accounts=False
        )
        response = synthesize.synthesize_instances(request.id)
        self.assertIsNone(response)
        self.assertFalse(models.Instance.objects.exists())

    def test_synthesize_instances_but_request_id_not_found(self):
        """Test early return if the SyntheticDataRequest does not exist."""
        self.assertFalse(models.SyntheticDataRequest.objects.exists())
        response = synthesize.synthesize_instances(1)
        self.assertIsNone(response)
        self.assertFalse(models.Instance.objects.exists())
