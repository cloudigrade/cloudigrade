"""Celery app for use in Django project."""
import django
from celery import Celery

# Django setup is required *before* Celery app can start correctly.
django.setup()

app = Celery('config')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
