from .base import *  # noqa


DEBUG = False
SECRET_KEY = env('DJANGO_SECRET_KEY', default='test')
TEST_RUNNER = 'django.test.runner.DiscoverRunner'

DATABASES = {
    'default': env.db(default='sqlite:////db.sqlite3')
}
