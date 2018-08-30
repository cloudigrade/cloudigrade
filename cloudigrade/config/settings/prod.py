"""Settings file meant for production like environments."""
from .base import *

# FIXME: After our OpenShift setup is finalized we should force debug to False.
DEBUG = env.bool('DJANGO_DEBUG', default=False)
SECRET_KEY = env('DJANGO_SECRET_KEY')
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS')

DATABASES['default']['NAME'] = env('DJANGO_DATABASE_NAME')
DATABASES['default']['HOST'] = env('DJANGO_DATABASE_HOST')
DATABASES['default']['USER'] = env('DJANGO_DATABASE_USER')
DATABASES['default']['PASSWORD'] = env('DJANGO_DATABASE_PASSWORD')

# Require these AWS_SQS_ variables to be set explicitly. No defaults.
AWS_SQS_REGION = env('AWS_SQS_REGION')
AWS_SQS_ACCESS_KEY_ID = env('AWS_SQS_ACCESS_KEY_ID')
AWS_SQS_SECRET_ACCESS_KEY = env('AWS_SQS_SECRET_ACCESS_KEY')

AWS_NAME_PREFIX = env('AWS_NAME_PREFIX',
                                default='cloudigrade-prod-')
CELERY_BROKER_TRANSPORT_OPTIONS['queue_name_prefix'] = AWS_NAME_PREFIX
CLOUDTRAIL_NAME_PREFIX = AWS_NAME_PREFIX
QUEUE_EXCHANGE_NAME = None

STATIC_ROOT = env('DJANGO_STATIC_ROOT', default='/srv/cloudigrade/static/')

if env('ENABLE_SENTRY', default=False):
    RAVEN_CONFIG = {
        'dsn': env('DJANGO_SENTRY_DSN'),
        'release': env('DJANGO_SENTRY_RELEASE'),
        'environment': env('DJANGO_SENTRY_ENVIRONMENT')
    }
    LOGGING['handlers']['sentry'] = {
        'level': env('DJANGO_SENTRY_LOG_LEVEL', default='ERROR'),
        'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler',
    }
    LOGGING['loggers']['']['handlers'].append('sentry')
