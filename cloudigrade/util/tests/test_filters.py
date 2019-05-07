"""Collection of tests for custom Jinja2 filters."""
import textwrap
from unittest.mock import MagicMock, Mock

from django.test import TestCase

from util import filters


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
        response = Mock()
        response.status_text = 'Bad Request'
        response.status_code = 400
        response.items.return_value = [
            ('Content-Type', 'application/json'),
            ('Vary', 'Accept'),
            ('Allow', 'POST, OPTIONS')
        ]
        response.json.return_value = {
            'non_field_errors': ['Unable to login with provided credentials.']
        }
        expected = \
            """
            HTTP/1.1 400 Bad Request
            Allow: POST, OPTIONS
            Content-Type: application/json
            Vary: Accept

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
        response = Mock()
        response.status_text = 'Not Found'
        response.status_code = 404
        response.items.return_value = [
            ('Content-Type', 'text/html'),
        ]
        response.json = Mock(side_effect=ValueError())
        response.content = b'<h1>Not Found</h1><p>The requested resource' \
                           b' was not found on this server.</p>'

        expected = \
            """
            HTTP/1.1 404 Not Found
            Content-Type: text/html

            <h1>Not Found</h1><p>The requested resource was not found on this server.</p>"""  # noqa: E501
        expected = textwrap.dedent(expected)[1:]  # trim whitespace
        actual = filters.stringify_http_response(response)
        self.assertEqual(actual, expected)

    def test_stringify_http_204_no_content(self):
        """Assert correct "no content" output of stringify_http_response."""
        response = Mock()
        response.status_text = 'No Content'
        response.status_code = 204
        response.items.return_value = [
            ('Allow', 'POST, OPTIONS'),
        ]
        response.json = Mock(side_effect=ValueError())
        response.content = None
        expected = \
            """
            HTTP/1.1 204 No Content
            Allow: POST, OPTIONS"""  # noqa: E501
        expected = textwrap.dedent(expected)[1:]  # trim whitespace
        actual = filters.stringify_http_response(response)
        self.assertEqual(expected, actual)

    def test_httpied_command_v2_includes_x_hr_identity(self):
        """Assert httpied_command with version=2 includes X_RH_IDENTITY."""
        uri = 'http://localhost/v2/ok'

        mock_request = MagicMock()
        mock_request.method = 'get'
        mock_request.user = None
        mock_request.build_absolute_uri.return_value = uri

        expected = (
            'http http://localhost/v2/ok "X-RH-IDENTITY:${HTTP_X_RH_IDENTITY}"'
        )
        actual = filters.httpied_command(mock_request, version=2)
        self.assertEqual(expected, actual)
