"""Custom Prometheus metrics definitions."""

import logging
from functools import partial

from django.conf import settings
from django.core.cache import cache
from prometheus_client import Gauge

from internal import redis
from util.cache import get_sqs_message_count_cache_key

logger = logging.getLogger(__name__)

CACHED_SQS_QUEUE_LENGTH_LABELS = [
    "houndigrade_results",
    "houndigrade_results_dlq",
    "cloudtrail_notifications",
    "cloudtrail_notifications_dlq",
]
CACHED_SQS_QUEUE_LENGTH_METRIC_NAME = "cloudigrade_sqs_queue_length"
CELERY_QUEUE_LENGTH_METRIC_NAME = "cloudigrade_celery_queue_length"


class CachedMetricsRegistry:
    """
    Registry of cached metrics.

    This class has a singleton-like class variable to ensure that underlying Prometheus
    client's metrics objects are only ever created once because the Prometheus client
    itself also requires that metrics are unique and only created and registered once.
    """

    _gauge_metrics = {}

    def initialize(self):
        """
        Initialize custom Prometheus metrics.

        This function should only be called once at app startup.
        """
        if self._gauge_metrics:
            logger.warning("Cannot reinitialize gauge metrics")
            return
        self._initialize_cached_sqs_queue_length_metrics()
        self._initialize_celery_queue_length_metrics()

    def _initialize_cached_sqs_queue_length_metrics(self):
        """Initialize cached SQS queue length metrics."""
        gauge = Gauge(
            CACHED_SQS_QUEUE_LENGTH_METRIC_NAME,
            "The approximate number of messages in AWS SQS queue.",
            labelnames=["queue_name"],
        )
        self._gauge_metrics[CACHED_SQS_QUEUE_LENGTH_METRIC_NAME] = gauge

        for label in CACHED_SQS_QUEUE_LENGTH_LABELS:
            cache_key = get_sqs_message_count_cache_key(label)
            gauge.labels(queue_name=label).set_function(
                partial(cache.get, cache_key, 0)
            )

    def _initialize_celery_queue_length_metrics(self):
        """Initialize Celery queue length metrics."""
        if not redis.redis_is_the_default_cache():
            # Currently this function only supports the Redis backend.
            return

        gauge = Gauge(
            CELERY_QUEUE_LENGTH_METRIC_NAME,
            "The number of messages in Celery broker queue.",
            labelnames=["queue_name"],
        )
        self._gauge_metrics[CELERY_QUEUE_LENGTH_METRIC_NAME] = gauge

        task_prefix = settings.CELERY_BROKER_TRANSPORT_OPTIONS.get(
            "global_keyprefix", ""
        )
        for task_route in settings.CELERY_TASK_ROUTES.values():
            if task_queue := task_route.get("queue"):
                queue_name = f"{task_prefix}{task_queue}"
                gauge.labels(queue_name=task_queue).set_function(
                    partial(redis.execute_command, "llen", [queue_name])
                )

    def get_registered_metrics_names(self):
        """Get list of registered metrics names."""
        return self._gauge_metrics.keys()
