"""Custom Prometheus metrics definitions."""

import logging
from dataclasses import dataclass
from functools import partial
from typing import Any

from django.core.cache import cache
from prometheus_client import Gauge

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

CUSTOM_GAUGE_METRICS = {}


def initialize_cached_metrics():
    """
    Initialize custom Prometheus metrics.

    This function should only be called once at app startup.
    """
    if CUSTOM_GAUGE_METRICS:
        logger.warning("Cannot reinitialize CUSTOM_GAUGE_METRICS")
        return
    for info in CACHED_GAUGE_METRICS_INFO:
        gauge = Gauge(info.metric_name, info.metric_description)
        gauge.set_function(partial(cache.get, info.cache_key, info.default))
        CUSTOM_GAUGE_METRICS[info.metric_name] = gauge
