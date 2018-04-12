"""Settings file meant for local development."""
from .base import *

DEBUG = env.bool('DJANGO_DEBUG', default=True)
SECRET_KEY = env('DJANGO_SECRET_KEY', default='local')

DATABASES['default']['PORT'] = env('DJANGO_DATABASE_PORT', default='15432')
