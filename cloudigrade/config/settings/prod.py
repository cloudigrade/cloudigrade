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

RABBITMQ_USER = env('RABBITMQ_USER')
RABBITMQ_PASSWORD = env('RABBITMQ_PASSWORD')
RABBITMQ_HOST = env('RABBITMQ_HOST')

RABBITMQ_URL = 'amqp://{}:{}@{}:{}/{}'.format(
    RABBITMQ_USER,
    RABBITMQ_PASSWORD,
    RABBITMQ_HOST,
    RABBITMQ_PORT,
    RABBITMQ_VHOST
)

CELERY_BROKER_URL = RABBITMQ_URL
STATIC_ROOT = env('DJANGO_STATIC_ROOT', default='/srv/cloudigrade/static/')
