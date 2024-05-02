"""Collection of tests for the internal.prometheus module."""

from unittest.mock import MagicMock, call, patch

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

    def test_initialize_db_table_size_metrics(self):
        """
        Test Database table size metrics are created as expected.

        Normally the _initialize_db_table_size_metrics function never creates the
        prometheus gauge by unit tests because unit tests are not configured to
        use a Postgres database. This test short-circuits the database check and
        sql statement executions to make metrics initialization possible.
        """
        fake_table_sizes = [
            [_faker.slug(), 1024 * _faker.random_int(min=1, max=256)],
            [_faker.slug(), 1024 * _faker.random_int(min=1, max=256)],
        ]
        expected_labels_calls = [
            call(table_name=table_name) for table_name, table_size in fake_table_sizes
        ]

        patched_custom_gauge_metrics = {}
        with patch(
            "internal.prometheus.CachedMetricsRegistry._gauge_metrics",
            patched_custom_gauge_metrics,
        ), patch("internal.prometheus.Gauge") as mock_gauge, patch(
            "internal.prometheus.CachedMetricsRegistry.db_is_pg",
        ) as mock_db_is_pg, patch(
            "internal.prometheus.connection"
        ) as mock_connection:
            mock_db_is_pg.return_value = True
            mock_cursor = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_cursor.execute.return_value = None
            mock_cursor.fetchall.return_value = fake_table_sizes

            from internal import prometheus

            registry = prometheus.CachedMetricsRegistry()
            registry._initialize_db_table_size_metrics()
            self.assertIn(
                prometheus.DB_TABLE_SIZE_METRIC_NAME,
                registry.get_registered_metrics_names(),
            )
            mock_gauge.assert_called_once()
            mock_gauge_instance = mock_gauge.return_value
            actual_labels_calls = mock_gauge_instance.labels.mock_calls
            for expected_labels_call in expected_labels_calls:
                self.assertIn(expected_labels_call, actual_labels_calls)

    def test_initialize_db_table_rows_metrics(self):
        """
        Test Database table rows metrics are created as expected.

        Normally the _initialize_db_table_rows_metrics function never creates the
        prometheus gauge by unit tests because unit tests are not configured to
        use a Postgres database. This test short-circuits the database check and
        sql statement executions to make metrics initialization possible.
        """
        fake_table_rows = [
            [_faker.slug(), _faker.random_int(min=1, max=16384)],
            [_faker.slug(), _faker.random_int(min=1, max=16384)],
            [_faker.slug(), _faker.random_int(min=1, max=16384)],
        ]
        expected_labels_calls = [
            call(table_name=table_name) for table_name, table_rows in fake_table_rows
        ]

        patched_custom_gauge_metrics = {}
        with patch(
            "internal.prometheus.CachedMetricsRegistry._gauge_metrics",
            patched_custom_gauge_metrics,
        ), patch("internal.prometheus.Gauge") as mock_gauge, patch(
            "internal.prometheus.CachedMetricsRegistry.db_is_pg",
        ) as mock_db_is_pg, patch(
            "internal.prometheus.connection"
        ) as mock_connection:
            mock_db_is_pg.return_value = True
            mock_cursor = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_cursor.execute.return_value = None
            mock_cursor.fetchall.return_value = fake_table_rows

            from internal import prometheus

            registry = prometheus.CachedMetricsRegistry()
            registry._initialize_db_table_rows_metrics()
            self.assertIn(
                prometheus.DB_TABLE_ROWS_METRIC_NAME,
                registry.get_registered_metrics_names(),
            )
            mock_gauge.assert_called_once()
            mock_gauge_instance = mock_gauge.return_value
            actual_labels_calls = mock_gauge_instance.labels.mock_calls
            for expected_labels_call in expected_labels_calls:
                self.assertIn(expected_labels_call, actual_labels_calls)
