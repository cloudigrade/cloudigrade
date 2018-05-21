"""Settings file meant for running tests."""
from .base import *

DEBUG = env.bool('DJANGO_DEBUG', default=False)
SECRET_KEY = env('DJANGO_SECRET_KEY', default='test')
TEST_RUNNER = 'django.test.runner.DiscoverRunner'

DATABASES['default'] = env.db(default='sqlite:////db.sqlite3')
AWS_SQS_QUEUE_NAME_PREFIX = env('AWS_SQS_QUEUE_NAME_PREFIX', default='cloudigrate-test-')
