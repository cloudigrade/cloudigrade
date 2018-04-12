"""Settings file meant for local development in docker compose."""
from .base import *

DEBUG = env.bool('DJANGO_DEBUG', default=True)
SECRET_KEY = env('DJANGO_SECRET_KEY', default='docker')

DATABASES['default']['HOST'] = env('DJANGO_DATABASE_HOST', default='db')

STATIC_ROOT = env('DJANGO_STATIC_ROOT', default='/srv/cloudigrade/static/')
