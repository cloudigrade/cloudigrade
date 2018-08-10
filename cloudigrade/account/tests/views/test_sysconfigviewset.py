"""Collection of tests for SysconfigViewSet."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from account.tests import helper as account_helper
from account.views import SysconfigViewSet
from util.tests import helper as util_helper


class SysconfigViewSetTest(TestCase):
    """SysconfigViewSet test case."""

    @patch('account.views._get_primary_account_id')
    def test_list_accounts_success(self, mock_get_primary_account_id):
        """Test listing account ids."""
        account_id = account_helper.generate_aws_account()
        mock_get_primary_account_id.return_value = account_id
        user = util_helper.generate_test_user()
        factory = APIRequestFactory()
        request = factory.get('/sysconfig/')
        force_authenticate(request, user=user)
        view = SysconfigViewSet.as_view(actions={'get': 'list'})

        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'aws_account_id': account_id})
