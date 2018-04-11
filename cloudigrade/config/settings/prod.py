from .base import *  # noqa

DEBUG = env.bool('DJANGO_DEBUG', default=False)
SECRET_KEY = env('DJANGO_SECRET_KEY')
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS')
DATABASES = {
    'default': {
        'ATOMIC_REQUESTS': env('DJANGO_ATOMIC_REQUESTS', default=True),
        'ENGINE': env('DJANGO_DATABASE_ENGINE', default='django.db.backends.postgresql_psycopg2'),
        'NAME': env('DJANGO_DATABASE_NAME'),
        'HOST': env('DJANGO_DATABASE_HOST'),
        'USER': env('DJANGO_DATABASE_USER'),
        'PASSWORD': env('DJANGO_DATABASE_PASSWORD'),
        'PORT': env('DJANGO_DATABASE_PORT', default=5432),
        'CONN_MAX_AGE': env('DJANGO_DATABASE_CONN_MAX_AGE', default=0),
    }
}

RABBITMQ_URL = env('RABBITMQ_URL')
CELERY_BROKER_URL = RABBITMQ_URL
STATIC_ROOT = env('DJANGO_STATIC_ROOT', default='/srv/cloudigrade/static/')
