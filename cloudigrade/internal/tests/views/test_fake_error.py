"""Collection of tests for the internal fake error view."""

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from internal.views import fake_error


class FakeErrorViewTest(TestCase):
    """Fake Error view test case."""

    def setUp(self):
        """Set up a shared request factory."""
        self.factory = APIRequestFactory()

    def assertExpectedResponse(self, response, status_code=500, contains=None):
        """Assert the response has the expected values."""
        if not contains and status_code == 500:
            contains = "A server error occurred"
        if not contains and status_code == 400:
            contains = "Invalid input"
        self.assertEqual(response.status_code, status_code)
        if contains:
            self.assertIn(contains, response.rendered_content.decode())

    def assertLogged(self, message, level, position, log_context):
        """Assert the message was logged."""
        self.assertGreater(
            len(log_context.output), position, msg="not enough logs captured"
        )
        self.assertTrue(log_context.output[position].startswith(f"{level}:"))
        self.assertIn(message, log_context.output[position])

    def test_fake_error_drf_exception_with_kwargs(self):
        """Test fake_error handles the requested DRF exception with kwargs."""
        name = "APIException"
        kwargs = {"detail": "i am a teapot"}

        request = self.factory.post(
            "/fake_error/", data={"name": name, "kwargs": kwargs}, format="json"
        )
        with self.assertLogs("internal.views", level="INFO") as log_context:
            response = fake_error(request)
        self.assertLogged(f"Fake {name}(**{kwargs})", "WARNING", 0, log_context)
        self.assertExpectedResponse(response, contains=kwargs["detail"])

    def test_fake_error_drf_exception_without_kwargs(self):
        """Test fake_error handles the requested DRF exception without kwargs."""
        name = "APIException"
        kwargs = {}  # not posted with the request but expected in log message

        request = self.factory.post("/fake_error/", data={"name": name})
        with self.assertLogs("internal.views", level="INFO") as log_context:
            response = fake_error(request)
        self.assertLogged(f"Fake {name}(**{kwargs})", "WARNING", 0, log_context)
        self.assertExpectedResponse(response)

    def test_fake_error_cloudigrade_exception_with_kwargs(self):
        """Test fake_error handles the requested cloudigrade exception with kwargs."""
        name = "NotReadyException"
        kwargs = {"message": "try again later"}

        request = self.factory.post(
            "/fake_error/", data={"name": name, "kwargs": kwargs}, format="json"
        )
        with self.assertLogs("internal.views", level="INFO") as log_context:
            response = fake_error(request)
        self.assertLogged(f"Fake {name}(**{kwargs})", "WARNING", 0, log_context)
        self.assertExpectedResponse(response)

    def test_fake_error_handles_bad_kwargs(self):
        """Test fake_error returns 400 if invalid kwargs are given for the exception."""
        name = "NotReadyException"
        kwargs = {"precious": "taters"}

        request = self.factory.post(
            "/fake_error/", data={"name": name, "kwargs": kwargs}, format="json"
        )
        with self.assertLogs("internal.views", level="INFO") as log_context:
            response = fake_error(request)
        self.assertLogged(f"Fake {name}(**{kwargs})", "WARNING", 0, log_context)
        self.assertLogged(
            "unexpected keyword argument 'precious'", "INFO", 1, log_context
        )
        self.assertExpectedResponse(response, status_code=400)

    def test_fake_error_handles_bad_exception_name(self):
        """Test fake_error returns 400 if exception name is not valid."""
        name = "ThisIsNotARealException"

        request = self.factory.post("/fake_error/", data={"name": name})
        with self.assertLogs("internal.views", level="INFO") as log_context:
            response = fake_error(request)
        self.assertLogged(f"{name} is not an exception.", "WARNING", 0, log_context)
        self.assertExpectedResponse(response, status_code=400)
