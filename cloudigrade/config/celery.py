"""Celery app for use in Django project."""
import logging
import uuid

import django
import environ
import sentry_sdk
from celery import Celery, current_task, signals
from sentry_sdk.integrations.celery import CeleryIntegration

from util.middleware import local

env = environ.Env()
logger = logging.getLogger(__name__)


logger.info("Starting celery.")
# Django setup is required *before* Celery app can start correctly.
django.setup()
logger.info("Django setup.")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
logger.info("Celery setup.")

if env("CELERY_ENABLE_SENTRY", default=False):
    logger.info("Enabling sentry.")
    sentry_sdk.init(
        dsn=env("CELERY_SENTRY_DSN"),
        environment=env("CELERY_SENTRY_ENVIRONMENT"),
        release=env("CELERY_SENTRY_RELEASE"),
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        integrations=[CeleryIntegration()],
    )
    logger.info("Sentry setup.")


@signals.before_task_publish.connect
def insert_request_id(headers=None, **kwargs):
    """
    Insert request_id into task headers.

    This is so we can log the same request_id in our task.
    If the task is not launched from a user request, generate
    a new request_id and use that.
    """
    request_id = getattr(local, "request_id", None)
    if request_id is None:
        request_id = uuid.uuid4()
    headers["request_id"] = request_id


@signals.task_prerun.connect
def setup_request_id(**kwargs):
    """Set request_id from current task header."""
    request_id = current_task.request.get("request_id", None)
    local.request_id = request_id


@signals.task_postrun.connect
def cleanup_request_id(**kwargs):
    """Clean up request_id from the thread."""
    local.request_id = None


@signals.setup_logging.connect
def on_celery_setup_logging(**kwargs):
    """
    Stop celery from overriding default logging setup.

    By default celery hijacks the root logger. The configuration setting
    CELERYD_HIJACK_ROOT_LOGGER only stops celery from updating the handler,
    celery still updates the formatter and we lose the filter.

    Since the formatter we want to use is the configured Django one,
    we can just configure celery to not touch logging.
    """
    pass
