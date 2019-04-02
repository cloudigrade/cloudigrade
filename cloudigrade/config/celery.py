"""Celery app for use in Django project."""
import logging

import django
import environ
import sentry_sdk
from celery import Celery
from sentry_sdk.integrations.celery import CeleryIntegration

env = environ.Env()
logger = logging.getLogger(__name__)


logger.info('Starting celery.')
# Django setup is required *before* Celery app can start correctly.
django.setup()
logger.info('Django setup.')

app = Celery('config')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
logger.info('Celery setup.')

if env('CELERY_ENABLE_SENTRY', default=False):
    logger.info('Enabling sentry.')
    sentry_sdk.init(
        dsn=env('CELERY_SENTRY_DSN'),
        environment=env('CELERY_SENTRY_ENVIRONMENT'),
        release=env('CELERY_SENTRY_RELEASE'),
        integrations=[CeleryIntegration()]
    )
    logger.info('Sentry setup.')
