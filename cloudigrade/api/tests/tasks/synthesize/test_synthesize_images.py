"""Collection of tests for api.tasks.synthesize.synthesize_images."""

from django.test import TestCase

from api import AWS_PROVIDER_STRING, CLOUD_PROVIDERS, models
from api.tasks import synthesize
from api.tests.tasks.synthesize import create_synthetic_data_request_without_post_save


class SynthesizeImagesTest(TestCase):
    """api.tasks.synthesize_images test case."""

    def test_synthesize_images(self):
        """
        Test happy path to create MachineImages for the SyntheticDataRequest.

        We expect requests for all CLOUD_PROVIDERS to have non-zero counts of their
        respective MachineImage types to be created successfully.
        """
        expected_total_image_count = 0
        for cloud_type in CLOUD_PROVIDERS:
            request = create_synthetic_data_request_without_post_save(
                cloud_type=cloud_type
            )
            expected_total_image_count += request.image_count
            response = synthesize.synthesize_images(request.id)
            self.assertEqual(response, request.id)
            request.refresh_from_db()
            self.assertGreater(request.image_count, 0)
            self.assertEqual(
                request.image_count,
                models.MachineImage.objects.filter(
                    syntheticdatarequest=request
                ).count(),
            )
            for image in models.MachineImage.objects.filter(
                syntheticdatarequest=request
            ):
                self.assertEqual(image.cloud_type, request.cloud_type)
        self.assertEqual(
            expected_total_image_count, models.MachineImage.objects.count()
        )

    def test_synthesize_images_but_no_cloud_account(self):
        """Test early return if the SyntheticDataRequest has no CloudAccount."""
        request = create_synthetic_data_request_without_post_save(
            cloud_type=AWS_PROVIDER_STRING, synthesize_cloud_accounts=False
        )
        response = synthesize.synthesize_images(request.id)
        self.assertIsNone(response)
        self.assertFalse(models.MachineImage.objects.exists())

    def test_synthesize_images_but_request_id_not_found(self):
        """Test early return if the SyntheticDataRequest does not exist."""
        self.assertFalse(models.SyntheticDataRequest.objects.exists())
        response = synthesize.synthesize_images(1)
        self.assertIsNone(response)
        self.assertFalse(models.MachineImage.objects.exists())
