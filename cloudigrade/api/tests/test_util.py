"""Collection of tests for the api.util module."""
from django.test import TestCase
from rest_framework.serializers import ValidationError

from api import util


class UtilTest(TestCase):
    """Miscellaneous test cases for api.util module functions."""

    def test_convert_param_to_int_with_int(self):
        """Test that convert_param_to_int returns int with int."""
        result = util.convert_param_to_int("test_field", 42)
        self.assertEqual(result, 42)

    def test_convert_param_to_int_with_str_int(self):
        """Test that convert_param_to_int returns int with str int."""
        result = util.convert_param_to_int("test_field", "42")
        self.assertEqual(result, 42)

    def test_convert_param_to_int_with_str(self):
        """Test that convert_param_to_int returns int with str."""
        with self.assertRaises(ValidationError):
            util.convert_param_to_int("test_field", "not_int")
