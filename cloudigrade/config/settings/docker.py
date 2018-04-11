from .base import *  # noqa

DEBUG = env.bool('DJANGO_DEBUG', default=True)
SECRET_KEY = env('DJANGO_SECRET_KEY', default='docker')
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['*'])

DATABASES = {
    'default': env.db(default='postgres://postgres:postgres@db:5432/postgres')
}

# Message and Task Queues

RABBITMQ_URL = env('RABBITMQ_URL', default='amqp://guest:guest@localhost:5672/%2F')
CELERY_BROKER_URL = RABBITMQ_URL

STATIC_ROOT = env('DJANGO_STATIC_ROOT', default='/srv/cloudigrade/static/')
