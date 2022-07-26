"""Collection of tests for the internal.prometheus module."""
import itertools
from unittest.mock import call, patch

import faker
from django.test import TestCase, override_settings

_faker = faker.Faker()


class InternalPrometheusTestCase(TestCase):
    """
    Test internal.prometheus.CachedMetricsRegistry.

    This is a difficult and strange thing to test because normally a call to initialize
    happens in InternalAppConfig.ready, but it appears to be impossible (within reason)
    to patch that behavior so that we override or mock it before Django tests actually
    run. Unfortunately, the AppConfig.ready functions are all called long before the
    test classes are loaded.

    So, we assume that InternalAppConfig.ready() may *already* have been called before
    these test functions even begin their setup.
    """

    def test_initialize(self):
        """
        Test initialize creates the expected Gauge object.

        Since we assume that "ready" may already have been called, we don't actually
        need to call initialize. We just assert the expected side-effects of calling
        initialize.
        """
        from internal import prometheus
        from prometheus_client import registry

        self.assertEqual(
            len(prometheus.CachedMetricsRegistry().get_registered_metrics_names()), 1
        )

        # Yes, _collector_to_names is pseudo-protected, but I couldn't find any other
        # supported mechanism to list all registered collectors.
        registered_names = itertools.chain(
            *list(registry.REGISTRY._collector_to_names.values())
        )
        self.assertIn(prometheus.CACHED_SQS_QUEUE_LENGTH_METRIC_NAME, registered_names)
        # Ditto for _names_to_collectors being protected. I wish I could find a better
        # supported mechanism to access the registry's internals.
        individual_metrics = registry.REGISTRY._names_to_collectors[
            prometheus.CACHED_SQS_QUEUE_LENGTH_METRIC_NAME
        ]._metrics
        self.assertEqual(
            len(individual_metrics), len(prometheus.CACHED_SQS_QUEUE_LENGTH_LABELS)
        )

    def test_initialize_multiple_calls(self):
        """
        Test initialize only creates the Gauge object once.

        Since we assume that "ready" may already have been called, we patch two things:
        the _gauge_metrics dict that contains known created metrics and the
        imported Gauge class. The former requires patching because it was already
        populated with entries by the ready function, and the latter requires patching
        because instantiating a new Gauge instance affects a *global* registry within
        prometheus_client that we must not affect within the scope of a test.
        """
        patched_custom_gauge_metrics = {}
        with patch(
            "internal.prometheus.CachedMetricsRegistry._gauge_metrics",
            patched_custom_gauge_metrics,
        ), patch("internal.prometheus.Gauge") as mock_gauge:
            from internal import prometheus

            registry = prometheus.CachedMetricsRegistry()

            # Initially _gauge_metrics should be empty.
            self.assertEqual(0, len(registry.get_registered_metrics_names()))

            registry.initialize()
            metrics_after_first_call = registry.get_registered_metrics_names()
            # After one call, _gauge_metrics should be populated.
            self.assertEqual(1, len(metrics_after_first_call))
            mock_gauge.assert_called_once()

            mock_gauge.reset_mock()

            registry.initialize()
            # After the second call, _gauge_metrics should be unchanged,
            # and there should be no more Gauge calls.
            metrics_after_second_call = registry.get_registered_metrics_names()
            self.assertEqual(1, len(metrics_after_second_call))
            self.assertEqual(metrics_after_first_call, metrics_after_second_call)
            mock_gauge.assert_not_called()

    def test_initialize_celery_queue_length_metrics(self):
        """
        Test Celery queue length metrics are created as expected.

        Normally the _initialize_celery_queue_length_metrics function never completes
        full execution by unit tests because unit tests are not configured to use the
        Redis cache backend. This test short-circuits Redis detection to make metrics
        initialization possible.
        """
        fake_celery_task_routes = {
            _faker.slug(): {"queue": _faker.slug()},
            _faker.slug(): {"queue": _faker.slug()},
        }
        expected_labels_calls = [
            call(queue_name=info["queue"]) for info in fake_celery_task_routes.values()
        ]

        patched_custom_gauge_metrics = {}
        with patch(
            "internal.prometheus.CachedMetricsRegistry._gauge_metrics",
            patched_custom_gauge_metrics,
        ), patch("internal.prometheus.Gauge") as mock_gauge, patch(
            "internal.prometheus.redis.redis_is_the_default_cache"
        ) as mock_redis_is_cache, override_settings(
            CELERY_TASK_ROUTES=fake_celery_task_routes
        ):
            mock_redis_is_cache.return_value = True

            from internal import prometheus

            registry = prometheus.CachedMetricsRegistry()
            registry._initialize_celery_queue_length_metrics()
            self.assertIn(
                prometheus.CELERY_QUEUE_LENGTH_METRIC_NAME,
                registry.get_registered_metrics_names(),
            )
            mock_gauge.assert_called_once()
            mock_gauge_instance = mock_gauge.return_value
            actual_labels_calls = mock_gauge_instance.labels.mock_calls
            for expected_labels_call in expected_labels_calls:
                self.assertIn(expected_labels_call, actual_labels_calls)
