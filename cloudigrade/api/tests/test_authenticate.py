"""Collection of tests targeting custom authentication modules."""
import base64
import json
from unittest.mock import Mock

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authentication import exceptions

from api.authentication import ThreeScaleAuthentication
from util.tests import helper as util_helper


class ThreeScaleAuthenticateTestCase(TestCase):
    """
    Test that 3scale authentication works as expected.

    When a request for a v2 endpoint comes in, we expect a base64 encoded
    HTTP_X_RH_IDENTITY header. When this header exists, the email field is
    what we use to determine the user.
    """

    def setUp(self):
        """Set up data for tests."""
        self.user_email = 'test@example.com'

        self.rh_header = util_helper.get_3scale_auth_header(
            account_number=self.user_email
        )
        self.three_scale_auth = ThreeScaleAuthentication()

    def test_3scale_authenticate(self):
        """Test that 3scale authentication with the correct header succeeds."""
        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: self.rh_header}

        user, auth = self.three_scale_auth.authenticate(request)

        self.assertTrue(auth)
        self.assertEqual(self.user_email, user.username)

    def test_3scale_authenticate_invalid_header(self):
        """Test that 3scale authentication with an invalid header fails."""
        bad_rh_header = base64.b64encode(b'Not JSON')

        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: bad_rh_header}

        with self.assertRaises(exceptions.AuthenticationFailed) as e:
            self.three_scale_auth.authenticate(request)
            self.assertIn('Authentication Failed', e.exception.args[0])

    def test_3scale_authenticate_header_bad_format(self):
        """Test that 3scale authentication with a bad json header fails."""
        rh_identity = {
            'user': {
                'email': self.user_email
            }
        }
        bad_rh_header = base64.b64encode(
            json.dumps(rh_identity).encode('utf-8')
        )

        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: bad_rh_header}

        with self.assertRaises(exceptions.AuthenticationFailed) as e:
            self.three_scale_auth.authenticate(request)
            self.assertIn('Authentication Failed', e.exception.args[0])

    def test_3scale_authenticate_no_header(self):
        """Test that 3scale authentication with no headers fails."""
        request = Mock()
        request.META = {}
        auth = self.three_scale_auth.authenticate(request)

        self.assertIsNone(auth)

    def test_3scale_authenticate_no_user(self):
        """Test that if an user doesn't exist, they are created."""
        users = User.objects.all()
        self.assertEqual(0, len(users))

        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: self.rh_header}

        user, auth = self.three_scale_auth.authenticate(request)

        self.assertTrue(auth)
        self.assertEqual(self.user_email, user.username)

        users = User.objects.all()

        self.assertEqual(1, len(users))
