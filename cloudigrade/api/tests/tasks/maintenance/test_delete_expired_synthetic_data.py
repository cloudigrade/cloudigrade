"""Collection of tests for tasks.maintenance.delete_expired_synthetic_data."""
from django.test import TestCase

from api import AWS_PROVIDER_STRING, models
from api.tasks import maintenance
from util.tests import helper as util_helper


class DeleteExpiredSyntheticDataTest(TestCase):
    """Celery task 'delete_expired_synthetic_data' test cases."""

    def setUp(self):
        """Set up common data."""
        self.long_ago = util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        self.run_time = util_helper.utc_dt(2022, 3, 25, 0, 0, 0)
        self.future = util_helper.utc_dt(3000, 4, 20, 0, 6, 9)

    def test_delete_expired_synthetic_data(self):
        """Test deleting expired SyntheticDataRequest."""
        models.SyntheticDataRequest.objects.create(
            cloud_type=AWS_PROVIDER_STRING, expires_at=self.long_ago
        )
        self.assertTrue(models.SyntheticDataRequest.objects.exists())
        with util_helper.clouditardis(self.run_time):
            maintenance.delete_expired_synthetic_data()
        self.assertFalse(models.SyntheticDataRequest.objects.exists())

    def test_delete_expired_synthetic_data_ignores_not_yet_expired(self):
        """Test ignoring not-yet-expired SyntheticDataRequest."""
        models.SyntheticDataRequest.objects.create(
            cloud_type=AWS_PROVIDER_STRING, expires_at=self.future
        )
        self.assertTrue(models.SyntheticDataRequest.objects.exists())
        with util_helper.clouditardis(self.run_time):
            maintenance.delete_expired_synthetic_data()
        self.assertTrue(models.SyntheticDataRequest.objects.exists())
