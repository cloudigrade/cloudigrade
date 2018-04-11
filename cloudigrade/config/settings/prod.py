from .base import *  # noqa

SECRET_KEY = env('DJANGO_SECRET_KEY')
ALLOWED_HOSTS = env('DJANGO_ALLOWED_HOSTS')
DATABASES = {
    'default': {
        'ENGINE': env('DJANGO_DATABASE_ENGINE', default=django.db.backends.postgresql_psycopg2),
        'NAME': env('DJANGO_DATABASE_NAME'),
        'HOST': env('DJANGO_DATABASE_HOST'),
        'USER': env('DJANGO_DATABASE_USER'),
        'PASSWORD': env('DJANGO_DATABASE_PASSWORD'),
        'PORT': env('DJANGO_DATABASE_PORT', default=5432),
        'CONN_MAX_AGE': env('DJANGO_DATABASE_CONN_MAX_AGE', default=0),
    }
}

RABBITMQ_URL = env('DJANGO_RABBITMQ_URL')
STATIC_ROOT = env('DJANGO_STATIC_ROOT', default='/srv/cloudigrade/static/')
