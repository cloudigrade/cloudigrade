"""Collection of tests for ``util.redhatcloud.identity`` module."""
import base64
import json

import faker
from django.test import TestCase

from util.redhatcloud import identity

_faker = faker.Faker()


class IdentityTest(TestCase):
    """Red Hat Cloud identity module test case."""

    def setUp(self):
        """Set up test data."""
        self.account_number = str(_faker.pyint())
        self.authentication_id = _faker.user_name()
        self.application_id = _faker.pyint()

    def test_generate_http_identity_headers(self):
        """Assert generation of an appropriate HTTP identity headers."""
        known_account_number = "1234567890"
        expected = {
            "X-RH-IDENTITY": (
                "eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDU2Nzg5MCJ9fQ=="
            )
        }
        actual = identity.generate_http_identity_headers(known_account_number)
        self.assertEqual(actual, expected)

    def test_generate_org_admin_http_identity_headers(self):
        """Assert generation of an appropriate HTTP identity headers."""
        known_account_number = "1234567890"
        expected = {
            "X-RH-IDENTITY": (
                "eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzND"
                "U2Nzg5MCIsICJ1c2VyIjogeyJpc19vcmdfYWRtaW4iOiB0cnVlfX19"
            )
        }
        actual = identity.generate_http_identity_headers(
            known_account_number, is_org_admin=True
        )
        self.assertEqual(actual, expected)

    def test_get_x_rh_identity_header_success(self):
        """Assert get_x_rh_identity_header succeeds for a valid header."""
        expected_value = {"identity": {"account_number": _faker.pyint()}}
        encoded_value = base64.b64encode(json.dumps(expected_value).encode("utf-8"))
        headers = ((_faker.slug(), _faker.slug()), ("x-rh-identity", encoded_value))

        extracted_value = identity.get_x_rh_identity_header(headers)
        self.assertEqual(extracted_value, expected_value)

    def test_get_x_rh_identity_header_missing(self):
        """Assert get_x_rh_identity_header returns empty dict if not found."""
        headers = ((_faker.slug(), _faker.slug()),)

        extracted_value = identity.get_x_rh_identity_header(headers)
        self.assertEqual(extracted_value, {})

    def test_get_x_rh_identity_header_invalid_header(self):
        """Assert invalid HTTP identity header returns None."""
        encoded_value = base64.b64encode(_faker.slug().encode("utf-8"))
        headers = ((_faker.slug(), _faker.slug()), ("x-rh-identity", encoded_value))

        extracted_value = identity.get_x_rh_identity_header(headers)
        self.assertEqual(extracted_value, None)
