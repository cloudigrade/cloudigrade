"""Collection of tests for tasks._build_container_definition."""
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from api.tasks import _build_container_definition


class BuildContainerDefinitionTest(TestCase):
    """Helper function '_build_container_definition' test cases."""

    @patch("api.tasks.settings")
    def test_build_container_definition_with_sentry(self, mock_s):
        """Assert successful build of definition with sentry params."""
        enable_sentry = True
        sentry_dsn = "dsn"
        sentry_release = "1.3.3.7"
        sentry_environment = "test"

        expected_result = [
            {"name": "HOUNDIGRADE_SENTRY_DSN", "value": sentry_dsn},
            {"name": "HOUNDIGRADE_SENTRY_RELEASE", "value": sentry_release},
            {"name": "HOUNDIGRADE_SENTRY_ENVIRONMENT", "value": sentry_environment,},
        ]

        mock_s.HOUNDIGRADE_ENABLE_SENTRY = enable_sentry
        mock_s.HOUNDIGRADE_SENTRY_DSN = sentry_dsn
        mock_s.HOUNDIGRADE_SENTRY_RELEASE = sentry_release
        mock_s.HOUNDIGRADE_SENTRY_ENVIRONMENT = sentry_environment

        task_command = ["-c", "aws", "-t", "ami-test", "/dev/sdba"]

        result = _build_container_definition(task_command)
        for entry in expected_result:
            self.assertIn(entry, result["environment"])

    def test_build_container_definition_without_sentry(self):
        """Assert successful build of definition with no sentry params."""
        task_command = ["-c", "aws", "-t", "ami-test", "/dev/sdba"]

        result = _build_container_definition(task_command)

        self.assertEqual(
            result["image"],
            f"{settings.HOUNDIGRADE_ECS_IMAGE_NAME}:"
            f"{settings.HOUNDIGRADE_ECS_IMAGE_TAG}",
        )
        self.assertEqual(result["command"], task_command)
        self.assertEqual(result["environment"][0]["value"], settings.AWS_SQS_REGION)
        self.assertEqual(
            result["environment"][1]["value"], settings.AWS_SQS_ACCESS_KEY_ID
        )
        self.assertEqual(
            result["environment"][2]["value"], settings.AWS_SQS_SECRET_ACCESS_KEY,
        )
        self.assertEqual(
            result["environment"][3]["value"], settings.HOUNDIGRADE_RESULTS_QUEUE_NAME,
        )
        self.assertEqual(
            result["environment"][4]["value"], settings.HOUNDIGRADE_EXCHANGE_NAME,
        )
        self.assertEqual(result["environment"][5]["value"], settings.CELERY_BROKER_URL)
