"""Collection of tests for ``util.exceptions`` module."""
from unittest.mock import Mock, patch

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase
from rest_framework.exceptions import APIException, NotFound
from rest_framework.exceptions import PermissionDenied as DrfPermissionDenied

from util import exceptions
from util.exceptions import NotImplementedAPIException


class ExceptionsTest(TestCase):
    """Exception module test case."""

    def test_api_exception_handler_apiexception_ok(self):
        """Assert APIException is passed through for handling."""
        mock_context = Mock()
        exc = APIException()
        with patch.object(exceptions, 'exception_handler') as mock_handler:
            response = exceptions.api_exception_handler(exc, mock_context)
            mock_handler.assert_called_with(exc, mock_context)
            self.assertEqual(response, mock_handler.return_value)

    def test_api_exception_handler_http404_replaced(self):
        """Assert Django's Http404 is replaced with DRF's NotFound."""
        mock_context = Mock()
        exc = Http404()
        with patch.object(exceptions, 'exception_handler') as mock_handler:
            response = exceptions.api_exception_handler(exc, mock_context)
            mock_call_args = mock_handler.call_args_list[0][0]
            self.assertIsInstance(mock_call_args[0], NotFound)
            self.assertEqual(mock_call_args[1], mock_context)
            self.assertEqual(response, mock_handler.return_value)

    def test_api_exception_handler_permissiondenied_replaced(self):
        """Assert Django's PermissionDenied is replaced with DRF's version."""
        mock_context = Mock()
        exc = PermissionDenied()
        with patch.object(exceptions, 'exception_handler') as mock_handler:
            response = exceptions.api_exception_handler(exc, mock_context)
            mock_call_args = mock_handler.call_args_list[0][0]
            self.assertIsInstance(mock_call_args[0], DrfPermissionDenied)
            self.assertEqual(mock_call_args[1], mock_context)
            self.assertEqual(response, mock_handler.return_value)

    def test_api_exception_handler_mystery_exception_replaced(self):
        """Assert mystery Exception is replaced with DRF's APIException."""
        mock_context = Mock()
        exc = Exception()
        with patch.object(exceptions, 'exception_handler') as mock_handler:
            response = exceptions.api_exception_handler(exc, mock_context)
            mock_call_args = mock_handler.call_args_list[0][0]
            self.assertIsInstance(mock_call_args[0], APIException)
            self.assertEqual(mock_call_args[1], mock_context)
            self.assertEqual(response, mock_handler.return_value)

    def test_api_exception_handler_NotImplementedError_replaced(self):
        """Assert NotImplementedError is replaced with our custom exception."""
        mock_context = Mock()
        exc = NotImplementedError()
        with patch.object(exceptions, 'exception_handler') as mock_handler:
            response = exceptions.api_exception_handler(exc, mock_context)
            mock_call_args = mock_handler.call_args_list[0][0]
            self.assertIsInstance(
                mock_call_args[0], NotImplementedAPIException
            )
            self.assertEqual(mock_call_args[1], mock_context)
            self.assertEqual(response, mock_handler.return_value)
