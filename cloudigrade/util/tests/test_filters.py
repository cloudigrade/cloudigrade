"""Collection of tests for custom Jinja2 filters."""
import textwrap

from django.test import TestCase

from account.tests.helper import SandboxedRestClient
from util import filters
from util.tests import helper


class Jinja2FiltersTest(TestCase):
    """Test custom Jinja2 filters."""

    def test_rst_codeblock_plain(self):
        """Assert correct output of rst_codeblock without code argument."""
        text = 'hello world'
        expected = '::\n\n    hello world'
        actual = filters.rst_codeblock(text)
        self.assertEqual(actual, expected)

    def test_rst_codeblock_code(self):
        """Assert correct output of rst_codeblock with code argument."""
        text = 'hello world'
        code = 'potato'
        expected = '.. code:: potato\n\n    hello world'
        actual = filters.rst_codeblock(text, code)
        self.assertEqual(actual, expected)

    def test_stringify_http_response_json(self):
        """Assert correct JSON output of stringify_http_response."""
        response = SandboxedRestClient().login(None, None)
        expected = \
            """
            HTTP/1.1 400 Bad Request
            Allow: POST, OPTIONS
            Content-Length: 67
            Content-Type: application/json
            Vary: Accept
            X-Frame-Options: SAMEORIGIN

            {
                "non_field_errors": [
                    "Unable to login with provided credentials."
                ]
            }
            """
        expected = textwrap.dedent(expected)[1:-1]  # trim whitespace
        actual = filters.stringify_http_response(response)
        self.assertEqual(actual, expected)

    def test_stringify_http_response_404(self):
        """Assert correct non-JSON output of stringify_http_response."""
        response = SandboxedRestClient().list_foo(None, None)
        expected = \
            """
            HTTP/1.1 404 Not Found
            Content-Length: 85
            Content-Type: text/html
            X-Frame-Options: SAMEORIGIN

            <h1>Not Found</h1><p>The requested URL /api/v1/foo/ was not found on this server.</p>"""  # noqa: E501
        expected = textwrap.dedent(expected)[1:]  # trim whitespace
        actual = filters.stringify_http_response(response)
        self.assertEqual(actual, expected)

    def test_stringify_http_204_no_content(self):
        """Assert correct "no content" output of stringify_http_response."""
        user = helper.generate_test_user()
        client = SandboxedRestClient()
        client._force_authenticate(user)
        response = client.logout()
        expected = \
            """
            HTTP/1.1 204 No Content
            Allow: POST, OPTIONS
            Content-Length: 0
            Vary: Accept
            X-Frame-Options: SAMEORIGIN"""  # noqa: E501
        expected = textwrap.dedent(expected)[1:]  # trim whitespace
        actual = filters.stringify_http_response(response)
        self.assertEqual(expected, actual)
