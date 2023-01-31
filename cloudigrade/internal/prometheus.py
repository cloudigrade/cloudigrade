"""Custom Prometheus metrics definitions."""

import logging
from functools import partial

from django.conf import settings
from django.db import connection
from prometheus_client import Gauge

from internal import redis

logger = logging.getLogger(__name__)

CELERY_QUEUE_LENGTH_METRIC_NAME = "cloudigrade_celery_queue_length"
DB_TABLE_SIZE_METRIC_NAME = "cloudigrade_db_table_size"
DB_TABLE_ROWS_METRIC_NAME = "cloudigrade_db_table_rows"


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
        self._initialize_celery_queue_length_metrics()
        self._initialize_db_table_size_metrics()
        self._initialize_db_table_rows_metrics()

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

    def _initialize_db_table_size_metrics(self):
        """Initialize Database table size metrics."""
        if not self.db_is_pg():
            # Currently only supports the Postgres database.
            logger.warning(
                "Database table size metrics is only available with Postgres"
            )
            return
        gauge = Gauge(
            DB_TABLE_SIZE_METRIC_NAME,
            "The size of the tables in bytes.",
            labelnames=["table_name"],
        )
        self._gauge_metrics[DB_TABLE_SIZE_METRIC_NAME] = gauge
        curs = connection.cursor()
        curs.execute(
            "SELECT tablename AS table_name,"
            " pg_total_relation_size(quote_ident(tablename)) AS table_size"
            " FROM (SELECT * FROM pg_catalog.pg_tables"
            " WHERE schemaname = 'public') t"
            " ORDER by table_name"
        )
        for table_name, table_size in curs.fetchall():
            gauge.labels(table_name=table_name).set(int(table_size))

    def _initialize_db_table_rows_metrics(self):
        """Initialize Database table number of rows metrics."""
        if not self.db_is_pg():
            # Currently only supports the Postgres database.
            logger.warning(
                "Database table rows metrics is only available with Postgres"
            )
            return
        gauge = Gauge(
            DB_TABLE_ROWS_METRIC_NAME,
            "The number of live rows in the tables.",
            labelnames=["table_name"],
        )
        self._gauge_metrics[DB_TABLE_ROWS_METRIC_NAME] = gauge
        curs = connection.cursor()
        curs.execute(
            "SELECT relname AS table_name,"
            " c.reltuples AS table_rows"
            " FROM pg_class c"
            " LEFT JOIN pg_namespace n"
            " ON (n.oid = c.relnamespace)"
            " WHERE nspname NOT IN ('pg_catalog', 'information_schema')"
            " AND c.relkind = 'r' AND nspname !~ '^pg_toast'"
            " ORDER by table_name"
        )
        for table_name, table_rows in curs.fetchall():
            gauge.labels(table_name=table_name).set(int(table_rows))

    def db_is_pg(self):
        """Return True if the connected database is postgresql."""
        return settings.DATABASES["default"]["ENGINE"].endswith("postgresql")

    def get_registered_metrics_names(self):
        """Get list of registered metrics names."""
        return self._gauge_metrics.keys()
