"""Collection of tests for custom DRF views in the account app."""
from unittest.mock import patch, Mock

from django.test import TestCase
from rest_framework import status, exceptions

from account.models import Account
from account.views import ReportViewSet
from util.tests import helper


class ReportViewSetTest(TestCase):
    """ReportViewSet test case."""

    def test_create_report_success(self):
        """Test report succeeds when given appropriate values."""
        mock_request = Mock()
        mock_request.data = {
            'account_id': helper.generate_dummy_aws_account_id(),
            'start': '2018-01-01T00:00:00',
            'end': '2018-02-01T00:00:00',
        }
        view = ReportViewSet()
        with patch.object(view, 'serializer_class') as mock_serializer_class:
            report_results = mock_serializer_class.return_value\
                .create.return_value
            response = view.create(mock_request)
            self.assertEqual(response.data, report_results)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_404s_missing_account(self):
        """Test report 404s when requesting an account that doesn't exist."""
        mock_request = Mock()
        mock_request.data = {
            'account_id': helper.generate_dummy_aws_account_id(),
            'start': '2018-01-01T00:00:00',
            'end': '2018-02-01T00:00:00',
        }
        view = ReportViewSet()
        with patch.object(view, 'serializer_class') as mock_serializer_class:
            mock_serializer_class.return_value.create = \
                Mock(side_effect=Account.DoesNotExist())
            with self.assertRaises(exceptions.NotFound):
                view.create(mock_request)
