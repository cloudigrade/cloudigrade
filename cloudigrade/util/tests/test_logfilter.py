"""Tests for Cloudigrade's custom log filters."""
import uuid
from unittest.mock import Mock, patch

from django.test import TestCase

from util.logfilter import RequestIDFilter


class RequestIDFilterTest(TestCase):
    """Tests for RequestIDFilter."""

    @patch('util.logfilter.local')
    def test_filter(self, mock_local):
        """Test that the filter adds request_id."""
        mock_local.request_id = uuid.uuid4()
        request_filter = RequestIDFilter()
        record = Mock()

        result = request_filter.filter(record)

        self.assertEqual(mock_local.request_id, record.request_id)
        self.assertTrue(result)
