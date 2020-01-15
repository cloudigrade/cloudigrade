"""Collection of tests for tasks.scale_down_cluster."""
from unittest.mock import patch

from django.test import TestCase

from api.clouds.aws.tasks import scale_down_cluster


class ScaleDownClusterTest(TestCase):
    """Celery task 'scale_down_cluster' test cases."""

    @patch("api.clouds.aws.tasks.aws")
    def test_scale_down_cluster_success(self, mock_aws):
        """Test the scale down cluster function."""
        mock_aws.scale_down.return_value = None
        scale_down_cluster()
