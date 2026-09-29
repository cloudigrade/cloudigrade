"""Tests for Clowder V2 Sources dependency endpoint resolution."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase


class SourcesV2ResolutionTest(SimpleTestCase):
    """Test _resolve_sources_v2_url from config.settings.base."""

    FALLBACK_URL = "http://sources-api.sources-ci.svc:8080"

    def _get_resolver(self):
        """Import the resolver function under test."""
        from config.settings.base import _resolve_sources_v2_url

        return _resolve_sources_v2_url

    def _make_v1_endpoint(self, app="sources-api", hostname="v1host", port=8000):
        """Create a mock V1 endpoint object."""
        return SimpleNamespace(app=app, hostname=hostname, port=port)

    def test_v2_endpoint_with_uri(self):
        """V2 endpoint present with URI → use V2 URI directly."""
        resolve = self._get_resolver()
        v2_ep = SimpleNamespace(
            uri="https://sources-api-svc.example.com:8443",
            authenticated=False,
            ca_certificate=None,
        )
        v1_endpoints = [self._make_v1_endpoint()]

        with patch(
            "config.settings.base.get_v2_dependency_endpoint", return_value=v2_ep
        ):
            result = resolve(self.FALLBACK_URL, v1_endpoints)

        self.assertEqual(result, "https://sources-api-svc.example.com:8443")

    def test_v2_endpoint_uri_trailing_slash_stripped(self):
        """V2 URI with trailing slash → stripped."""
        resolve = self._get_resolver()
        v2_ep = SimpleNamespace(
            uri="http://sources:8000/",
            authenticated=False,
            ca_certificate=None,
        )

        with patch(
            "config.settings.base.get_v2_dependency_endpoint", return_value=v2_ep
        ):
            result = resolve(self.FALLBACK_URL, [])

        self.assertEqual(result, "http://sources:8000")

    def test_v2_absent_falls_back_to_v1(self):
        """V2 returns None → fall back to V1 endpoints."""
        resolve = self._get_resolver()
        v1_endpoints = [self._make_v1_endpoint(hostname="v1-sources", port=9090)]

        with patch(
            "config.settings.base.get_v2_dependency_endpoint", return_value=None
        ):
            result = resolve(self.FALLBACK_URL, v1_endpoints)

        self.assertEqual(result, "http://v1-sources:9090")

    def test_v2_empty_uri_falls_back_to_v1(self):
        """V2 endpoint exists but URI is empty → fall back to V1."""
        resolve = self._get_resolver()
        v2_ep = SimpleNamespace(uri="", authenticated=False, ca_certificate=None)
        v1_endpoints = [self._make_v1_endpoint(hostname="v1host", port=8080)]

        with patch(
            "config.settings.base.get_v2_dependency_endpoint", return_value=v2_ep
        ):
            result = resolve(self.FALLBACK_URL, v1_endpoints)

        self.assertEqual(result, "http://v1host:8080")

    def test_v1_no_sources_endpoint_falls_back_to_env(self):
        """V2 absent + V1 has no sources-api endpoint → env fallback."""
        resolve = self._get_resolver()
        v1_endpoints = [self._make_v1_endpoint(app="postigrade")]

        with patch(
            "config.settings.base.get_v2_dependency_endpoint", return_value=None
        ):
            result = resolve(self.FALLBACK_URL, v1_endpoints)

        self.assertEqual(result, self.FALLBACK_URL)

    def test_v1_empty_list_falls_back_to_env(self):
        """V2 absent + V1 endpoints empty → env fallback."""
        resolve = self._get_resolver()

        with patch(
            "config.settings.base.get_v2_dependency_endpoint", return_value=None
        ):
            result = resolve(self.FALLBACK_URL, [])

        self.assertEqual(result, self.FALLBACK_URL)

    def test_v2_none_uri_attribute_falls_back(self):
        """V2 endpoint with uri=None → fall back to V1."""
        resolve = self._get_resolver()
        v2_ep = SimpleNamespace(uri=None, authenticated=False, ca_certificate=None)
        v1_endpoints = [self._make_v1_endpoint(hostname="fallback", port=5555)]

        with patch(
            "config.settings.base.get_v2_dependency_endpoint", return_value=v2_ep
        ):
            result = resolve(self.FALLBACK_URL, v1_endpoints)

        self.assertEqual(result, "http://fallback:5555")

    def test_v2_called_with_correct_keys(self):
        """Verify get_v2_dependency_endpoint called with 'sources-api', 'svc'."""
        resolve = self._get_resolver()

        with patch(
            "config.settings.base.get_v2_dependency_endpoint", return_value=None
        ) as mock_v2:
            resolve(self.FALLBACK_URL, [])

        mock_v2.assert_called_once_with("sources-api", "svc")
