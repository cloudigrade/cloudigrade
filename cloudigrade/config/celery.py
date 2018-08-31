"""Celery app for use in Django project."""
import django
import environ
import raven
from celery import Celery
from raven.contrib.celery import register_logger_signal, register_signal

env = environ.Env()

# Django setup is required *before* Celery app can start correctly.
django.setup()

app = Celery('config')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

if env('CELERY_ENABLE_SENTRY', default=False):
    client = raven.Client(dsn=env('CELERY_SENTRY_DSN'),
                          environment=env('CELERY_SENTRY_ENVIRONMENT'),
                          release=env('CELERY_SENTRY_RELEASE'))

    # register a custom filter to filter out duplicate logs
    register_logger_signal(client)

    # hook into the Celery error handler
    register_signal(client)
