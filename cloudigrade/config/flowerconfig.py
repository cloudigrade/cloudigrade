"""Flower app for use with Celery."""
from django.conf import settings

# Note: port does not seem to be honored from the config file, so
#       we still invoke flower with --port=8000 instead of driving
#       this directly from the port exposed in cdappconfig.json.
port = settings.FLOWER_PORT
basic_auth = settings.FLOWER_BASIC_AUTH
broker_api = settings.FLOWER_BROKER_API
