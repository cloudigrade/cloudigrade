"""Collection of tests for custom DRF permissions in the account app."""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


class PermissionsTest(TestCase):
    """Permissions test case."""

    def setUp(self):
        """Set Up function for the test case."""
        self.client = APIClient()
        user = User.objects.create_user(username='test', password='test')
        self.token = Token.objects.create(user=user)

    def test_is_authenticated_pass(self):
        """Test that an options call is allowed unauthenticated."""
        request = self.client.options('/auth/me/')
        self.assertEqual(request.status_code, 200)

    def test_is_authenticated_fail_get(self):
        """Test that a get call is not allowed unauthenticated."""
        request = self.client.get('/auth/me/')
        self.assertEqual(request.status_code, 401)

    def test_is_authenticated_pass_token(self):
        """Test that an options call is allowed authenticated."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        request = self.client.options('/auth/me/')
        self.assertEqual(request.status_code, 200)
        self.assertEqual(
            request.request.get('HTTP_AUTHORIZATION'),
            f'Token {self.token.key}')
        self.client.credentials()

    def test_is_authenticated_pass_get_token(self):
        """Test that a get call is allowed authenticated."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        request = self.client.get('/auth/me/')
        self.assertEqual(request.status_code, 200)
        self.assertEqual(
            request.request.get('HTTP_AUTHORIZATION'),
            f'Token {self.token.key}')
        self.client.credentials()
