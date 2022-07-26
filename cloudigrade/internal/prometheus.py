"""Custom Prometheus metrics definitions."""

import logging
from dataclasses import dataclass
from functools import partial
from typing import Any

from django.conf import settings
from django.core.cache import cache
from prometheus_client import Gauge

from internal import redis
from util.cache import get_sqs_message_count_cache_key

logger = logging.getLogger(__name__)


@dataclass
class CachedGaugeMetricInfo:
    """Describe the relationship between a cache key and Prometheus gauge metric."""

    metric_name: str
    metric_description: str
    cache_key: str
    default: Any


CACHED_GAUGE_METRICS_INFO = [
    CachedGaugeMetricInfo(
        "houndigrade_results_message_count",
        "approximate message count for houndigrade results queue",
        get_sqs_message_count_cache_key("houndigrade_results"),
        0,
    ),
    CachedGaugeMetricInfo(
        "houndigrade_results_dlq_message_count",
        "approximate message count for houndigrade results DLQ",
        get_sqs_message_count_cache_key("houndigrade_results_dlq"),
        0,
    ),
    CachedGaugeMetricInfo(
        "cloudtrail_notifications_message_count",
        "approximate message count for CloudTrail notifications queue",
        get_sqs_message_count_cache_key("cloudtrail_notifications"),
        0,
    ),
    CachedGaugeMetricInfo(
        "cloudtrail_notifications_dlq_message_count",
        "approximate message count for CloudTrail notifications DLQ",
        get_sqs_message_count_cache_key("cloudtrail_notifications_dlq"),
        0,
    ),
]

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
        self._initialize_cached_metrics()
        self._initialize_celery_queue_length_metrics()

    def _initialize_cached_metrics(self):
        """Initialize cached metrics."""
        for info in CACHED_GAUGE_METRICS_INFO:
            gauge = Gauge(info.metric_name, info.metric_description)
            gauge.set_function(partial(cache.get, info.cache_key, info.default))
            self._gauge_metrics[info.metric_name] = gauge

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
