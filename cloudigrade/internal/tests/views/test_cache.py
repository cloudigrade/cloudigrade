"""Collection of tests for Internal cache."""

from unittest.mock import patch

import faker
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from internal.views import cache_keys

_faker = faker.Faker()


class CacheViewTest(TestCase):
    """Cache View test case."""

    def setUp(self):
        """Set up a bunch shared test data."""
        self.factory = APIRequestFactory()

    def test_cache_set_success(self):
        """Test happy path success for setting a cache key."""
        key = _faker.word()
        value = _faker.slug()
        request = self.factory.post(
            f"/cache/{key}", data={"value": value}, format="json"
        )

        response = cache_keys(request, key)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(cache.get(key), value)

    def test_cache_get_success(self):
        """Test happy path success for getting a cache key."""
        key = _faker.word()
        value = _faker.slug()
        cache.set(key, value)
        request = self.factory.get(f"/cache/{key}")

        response = cache_keys(request, key)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["value"], value)

    def test_cache_get_success_with_falsy_value(self):
        """
        Test getting a cache key for a falsy value (int 0).

        This more thoroughly exercises the "is not None" condition because we may be
        storing falsy values like 0 in the cache, and we expect to see those correctly
        in the internal API's responses. Previously we did not explicitly check against
        None, and falsy values could unexpectedly return a 404 Not Found response.
        """
        key = _faker.word()
        value = 0
        cache.set(key, value)
        request = self.factory.get(f"/cache/{key}")

        response = cache_keys(request, key)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["value"], value)

    def test_cache_get_success_with_timeout(self):
        """Test get of a key returns the key, its value and timeout."""
        key = _faker.word()
        value = _faker.slug()
        timeout = _faker.random_int(min=600, max=3600)
        cache.set(key, value, timeout)
        request = self.factory.get(f"/cache/{key}")

        response = cache_keys(request, key)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["key"], key)
        self.assertEqual(response.data["value"], value)
        self.assertTrue(timeout - 2 <= response.data["timeout"] <= timeout)

    def test_cache_set_missing_value(self):
        """Test cache set with missing value."""
        key = _faker.word()
        request = self.factory.post(f"/cache/{key}", data={}, format="json")

        response = cache_keys(request, key)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data[0], "value field is required")

    def test_cache_get_invalid_key(self):
        """Test get of an invalid key returns a 404."""
        key = _faker.word()
        request = self.factory.get(f"/cache/{key}")

        response = cache_keys(request, key)
        self.assertEqual(response.status_code, 404)

    @patch("django.core.cache.cache.set")
    def test_cache_set_timeout_honored(self, mock_cache):
        """Test set of a key with timeout is honored."""
        key = _faker.word()
        value = _faker.slug()
        timeout = _faker.random_int(min=600, max=3600)
        request = self.factory.post(
            f"/cache/{key}", data={"value": value, "timeout": timeout}, format="json"
        )

        response = cache_keys(request, key)
        self.assertEqual(response.status_code, 200)
        mock_cache.assert_called_with(key, value, timeout=timeout)
