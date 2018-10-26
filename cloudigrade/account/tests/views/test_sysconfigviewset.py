"""Collection of tests for SysconfigViewSet."""
import http
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from account.tests import helper as account_helper
from account.views import SysconfigViewSet
from util import aws
from util.tests import helper as util_helper


class SysconfigViewSetTest(TestCase):
    """SysconfigViewSet test case."""

    def setUp(self):
        """Set up data for each test."""
        self.aws_account_id = account_helper.generate_aws_account()
        self.regular_user = util_helper.generate_test_user()
        self.super_user = util_helper.generate_test_user(is_superuser=True)

    def get_sysconfig_response(self, as_user=None):
        """
        Get the sysconfig response as the specified user.

        Args:
            as_user (User): optional Django User to use for authentication

        Returns:
            Response. The response of the optionally-authenticated request.

        """
        factory = APIRequestFactory()
        request = factory.get('/sysconfig/')
        if as_user:
            force_authenticate(request, user=as_user)
        view = SysconfigViewSet.as_view(actions={'get': 'list'})
        with patch('account.views._get_primary_account_id') as \
                mock_get_primary_account_id:
            mock_get_primary_account_id.return_value = self.aws_account_id
            response = view(request)
        return response

    def assert_sysconfig_response(self, response):
        """Assert the sysconfig response includes typical expected data."""
        self.assertEqual(response.status_code, http.HTTPStatus.OK)
        self.assertEqual(response.data['aws_account_id'], self.aws_account_id)
        self.assertEqual(
            response.data['aws_policies']['traditional_inspection'],
            aws.sts.cloudigrade_policy
        )
        self.assertEqual(
            response.data['version'], settings.CLOUDIGRADE_VERSION)

    def test_get_sysconfig_no_auth_unauthorized(self):
        """Test getting the sysconfig without authentication."""
        response = self.get_sysconfig_response()
        self.assertEqual(response.status_code, http.HTTPStatus.UNAUTHORIZED)

    def test_get_sysconfig_as_regular_user_ok(self):
        """Test getting the sysconfig authenticated as a regular user."""
        response = self.get_sysconfig_response(self.regular_user)
        self.assert_sysconfig_response(response)

    def test_get_sysconfig_as_super_user_ok(self):
        """Test getting the sysconfig authenticated as a super user."""
        response = self.get_sysconfig_response(self.super_user)
        self.assert_sysconfig_response(response)
