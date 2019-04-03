"""Tests for cloudigrade's custom middleware."""
from unittest.mock import Mock

from django.conf import settings
from django.test import TestCase

from util.middleware import RequestIDLoggingMiddleware, local


class RequestIDLoggingMiddlewareTests(TestCase):
    """Tests for Cloudigrade's custom request_id logging middleware."""

    def setUp(self):
        """Variables shared across tests."""
        get_response = Mock(return_value={})
        self.middleware = RequestIDLoggingMiddleware(get_response)

        self.request = Mock()
        self.request.path = '/badURL/'
        self.request.session = {}

    def test_request_id_set(self):
        """Test that request_id is set when request is processed."""
        self.middleware.process_request(self.request)
        request_id = local.request_id
        self.assertIsNotNone(request_id)

    def test_response_headers(self):
        """Test that response sets the CLOUDIGRADE_REQUEST_HEADER header."""
        self.middleware.process_request(self.request)
        request_id = local.request_id

        response = self.middleware.process_response(self.request, {})
        self.assertEqual(request_id,
                         response.get(settings.CLOUDIGRADE_REQUEST_HEADER)
                         )

        # Assert thread local request_id is cleaned up
        self.assertFalse(hasattr(local, 'request_id'))

    def test_call(self):
        """Test CLOUDIGRADE_REQUEST_HEADER is set when middleware is called."""
        response = self.middleware(self.request)
        self.assertIsNotNone(
            response.get(settings.CLOUDIGRADE_REQUEST_HEADER)
        )
