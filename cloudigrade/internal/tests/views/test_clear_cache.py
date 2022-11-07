"""Collection of tests for Clearing Internal cache."""
import faker
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from internal.views import clear_cache

_faker = faker.Faker()


class ClearCacheTest(TestCase):
    """Clear cache view test case."""

    def setUp(self):
        """Set up a bunch shared test data."""
        self.factory = APIRequestFactory()

    def test_clear_cache(self):
        """Test happy path success for clearing the cache."""
        key1, val1 = _faker.word(), _faker.slug()
        key2, val2 = _faker.word(), _faker.slug()

        cache.set(key1, val1)
        cache.set(key2, val2)

        self.assertEqual(cache.get(key1), val1)
        self.assertEqual(cache.get(key2), val2)

        request = self.factory.post("/clear_cache")

        response = clear_cache(request)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data)

        self.assertEqual(cache.get(key1), None)
        self.assertEqual(cache.get(key2), None)
