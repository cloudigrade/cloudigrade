"""Collection of tests for tasks.maintenance.check_and_cache_sqs_queues_lengths."""
from unittest.mock import patch

import faker
from django.core.cache import cache
from django.test import TestCase, override_settings

from api.tasks import maintenance
from util import aws

_faker = faker.Faker()
_base_sqs_url = "http://localhost/sqs/"


class UnexpectedException(Exception):
    """Dummy exception for testing."""


def get_sqs_queue_url(queue_name, *args, **kwargs):
    """Override behavior of sqs.get_sqs_queue_url."""
    return f"{_base_sqs_url}{queue_name}"


class CheckAndCacheSqsQueueLengthsTest(TestCase):
    """tasks.maintenance.check_and_cache_sqs_queues_lengths test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.houndigrade_queue_name = f"houndigrade_{_faker.slug()}"
        self.houndigrade_dlq_name = aws.get_sqs_queue_dlq_name(
            self.houndigrade_queue_name
        )
        self.houndigrade_queue_url = get_sqs_queue_url(self.houndigrade_queue_name)
        self.houndigrade_dlq_url = get_sqs_queue_url(self.houndigrade_dlq_name)

        self.cloudtrail_queue_name = f"cloudtrail_{_faker.slug()}"
        self.cloudtrail_dlq_name = aws.get_sqs_queue_dlq_name(
            self.cloudtrail_queue_name
        )
        self.cloudtrail_queue_url = get_sqs_queue_url(self.cloudtrail_queue_name)
        self.cloudtrail_dlq_url = get_sqs_queue_url(self.cloudtrail_dlq_name)

        # It's very important to clear cache between these test runs because different
        # tests expect values *not* to be set whereas other tests may set them.
        cache.clear()

    def test_check_and_cache_sqs_queues_lengths(self):
        """
        Test happy path for check_and_cache_sqs_queues_lengths.

        We expect to get valid integers for all queues and to cache those values.
        """
        expected_counts = {
            "houndigrade_results": _faker.random_int(),
            "houndigrade_results_dlq": _faker.random_int(),
            "cloudtrail_notifications": _faker.random_int(),
            "cloudtrail_notifications_dlq": _faker.random_int(),
        }

        with override_settings(
            AWS_CLOUDTRAIL_EVENT_QUEUE_NAME=self.cloudtrail_queue_name,
            HOUNDIGRADE_RESULTS_QUEUE_NAME=self.houndigrade_queue_name,
        ), patch.object(maintenance, "aws") as mock_aws:
            mock_aws.get_sqs_approximate_number_of_messages.side_effect = (
                expected_counts.values()
            )
            # patch back in the original get_sqs_queue_dlq_name
            mock_aws.get_sqs_queue_dlq_name = aws.get_sqs_queue_dlq_name
            # patch back in our custom simplified get_sqs_queue_url
            mock_aws.get_sqs_queue_url = get_sqs_queue_url

            maintenance.check_and_cache_sqs_queues_lengths()

        for key, value in expected_counts.items():
            cache_key = maintenance.get_sqs_message_count_cache_key(key)
            cache_value = cache.get(cache_key)
            self.assertEqual(
                value,
                cache_value,
                f"expected and cached values are not equal for '{key}'",
            )

    def test_check_and_cache_sqs_queues_lengths_handles_missing_queues(self):
        """
        Test check_and_cache_sqs_queues_lengths does not set value if missing response.

        If the queue does not exist or the call to AWS raises an unexpected exception
        or error code, we log a message and skip updating the cache for that queue.
        """
        # Preload the cache with an "old" value that should not be replaced.
        old_cloudtrail_notifications_count = _faker.random_int()
        cache.set(
            maintenance.get_sqs_message_count_cache_key("cloudtrail_notifications"),
            old_cloudtrail_notifications_count,
        )

        expected_counts = {
            "houndigrade_results": _faker.random_int(),
            "houndigrade_results_dlq": None,
            "cloudtrail_notifications": old_cloudtrail_notifications_count,
            "cloudtrail_notifications_dlq": _faker.random_int(),
        }

        # Slightly different list represents the responses from AWS
        # because we want to simulate no response for "cloudtrail_notifications".
        aws_counts = list(expected_counts.values())
        aws_counts[2] = None

        with override_settings(
            AWS_CLOUDTRAIL_EVENT_QUEUE_NAME=self.cloudtrail_queue_name,
            HOUNDIGRADE_RESULTS_QUEUE_NAME=self.houndigrade_queue_name,
        ), self.assertLogs(
            "api.tasks.maintenance", level="ERROR"
        ) as logging_watcher, patch.object(
            maintenance, "aws"
        ) as mock_aws:
            mock_aws.get_sqs_approximate_number_of_messages.side_effect = aws_counts
            # patch back in the original get_sqs_queue_dlq_name
            mock_aws.get_sqs_queue_dlq_name = aws.get_sqs_queue_dlq_name
            # patch back in our custom simplified get_sqs_queue_url
            mock_aws.get_sqs_queue_url = get_sqs_queue_url

            maintenance.check_and_cache_sqs_queues_lengths()

        self.assertIn("Could not get approximate", logging_watcher.output[0])
        self.assertIn(self.houndigrade_dlq_name, logging_watcher.output[0])
        self.assertIn(self.houndigrade_dlq_url, logging_watcher.output[0])
        self.assertIn("Could not get approximate", logging_watcher.output[1])
        self.assertIn(self.cloudtrail_queue_name, logging_watcher.output[1])
        self.assertIn(self.cloudtrail_queue_url, logging_watcher.output[1])

        for key, value in expected_counts.items():
            cache_key = maintenance.get_sqs_message_count_cache_key(key)
            cache_value = cache.get(cache_key)
            self.assertEqual(
                value,
                cache_value,
                f"expected and cached values are not equal for '{key}'",
            )
