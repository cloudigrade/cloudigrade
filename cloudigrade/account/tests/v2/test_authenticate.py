"""Collection of tests targeting custom authentication modules."""
import base64
import json
from unittest.mock import Mock

from django.contrib.auth.models import User
from django.test import TestCase

from account.v2.authentication import ThreeScaleAuthentication
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
            email=self.user_email
        )
        self.three_scale_auth = ThreeScaleAuthentication()

    def test_3scale_authenticate(self):
        """Test that 3scale authentication with the correct header succeeds."""
        request = Mock()
        request.META = {'HTTP_X_RH_IDENTITY': self.rh_header}

        user, auth = self.three_scale_auth.authenticate(request)

        self.assertTrue(auth)
        self.assertEqual(self.user_email, user.username)

    def test_3scale_authenticate_invalid_header(self):
        """Test that 3scale authentication with an invalid header fails."""
        rh_identity = {
            'user': {
                'email': self.user_email
            }
        }
        bad_rh_header = base64.b64encode(
            json.dumps(rh_identity).encode('utf-8')
        )

        request = Mock()
        request.META = {'HTTP_X_RH_IDENTITY': bad_rh_header}

        auth = self.three_scale_auth.authenticate(request)

        self.assertIsNone(auth)

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
        request.META = {'HTTP_X_RH_IDENTITY': self.rh_header}

        user, auth = self.three_scale_auth.authenticate(request)

        self.assertTrue(auth)
        self.assertEqual(self.user_email, user.username)

        users = User.objects.all()

        self.assertEqual(1, len(users))
