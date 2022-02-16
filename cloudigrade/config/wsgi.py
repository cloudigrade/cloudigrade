"""WSGI config for cloudigrade project."""
import os

from django.core.wsgi import get_wsgi_application

from internal import metrics


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()

metrics.CeleryMetrics().listener()
