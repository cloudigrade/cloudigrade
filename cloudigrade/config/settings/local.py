"""Settings file meant for local development."""
from .base import *

DEBUG = env.bool("DJANGO_DEBUG", default=True)
SECRET_KEY = env("DJANGO_SECRET_KEY", default="local")
INSTALLED_APPS = INSTALLED_APPS + ["django_extensions"]
