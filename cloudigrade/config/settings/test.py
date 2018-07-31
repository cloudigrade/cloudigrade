"""Settings file meant for running tests."""
from .base import *

DEBUG = env.bool('DJANGO_DEBUG', default=False)
SECRET_KEY = env('DJANGO_SECRET_KEY', default='test')
TEST_RUNNER = 'django.test.runner.DiscoverRunner'

DATABASES['default'] = env.db(default='sqlite:////db.sqlite3')
AWS_NAME_PREFIX = env('AWS_NAME_PREFIX', default='cloudigrade-test-')
CELERY_BROKER_TRANSPORT_OPTIONS['queue_name_prefix'] = AWS_NAME_PREFIX
CLOUDTRAIL_NAME_PREFIX = AWS_NAME_PREFIX

