"""Collection of tests for API views for the account app."""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from dj_auth.views import TokenCreateView


class TokenCreateViewTests(TestCase):
    """TokenCreateViewSet test cases."""

    def setUp(self):
        """Set up data for test cases."""
        self.factory = APIRequestFactory()
        self.password = 'Testpassword1'

    def test_create_token_response_with_superuser(self):
        """Test the TokenCreate response for a superuser."""
        user = User.objects.create_user(username='testSuperUser',
                                        password=self.password,
                                        is_superuser=True)

        # not using user.password because it gets base64 encoded
        data = {
            'username': user.username,
            'password': self.password
        }

        request = self.factory.post('/auth/token/create/', data=data)

        view = TokenCreateView.as_view()
        response = view(request)

        self.assertTrue(response.data['is_superuser'])
        self.assertIn('auth_token', response.data)
        self.assertEqual(response.status_code, 200)

    def test_create_token_response_with_non_superuser(self):
        """Test the TokenCreate response for a regular user."""
        user = User.objects.create_user(username='testSuperUser',
                                        password=self.password,
                                        is_superuser=False)

        # not using user.password because it gets base64 encoded
        data = {
            'username': user.username,
            'password': self.password
        }

        request = self.factory.post('/auth/token/create/', data=data)

        view = TokenCreateView.as_view()
        response = view(request)

        self.assertFalse(response.data['is_superuser'])
        self.assertIn('auth_token', response.data)
        self.assertEqual(response.status_code, 200)
