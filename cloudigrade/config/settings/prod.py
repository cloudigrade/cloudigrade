"""Settings file meant for production like environments."""
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *

IS_PRODUCTION = CLOUDIGRADE_ENVIRONMENT == "prod"

# FIXME: After our OpenShift setup is finalized we should force debug to False.
DEBUG = env.bool("DJANGO_DEBUG", default=False)
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

DATABASES["default"]["NAME"] = env("DJANGO_DATABASE_NAME")
DATABASES["default"]["HOST"] = env("DJANGO_DATABASE_HOST")
DATABASES["default"]["USER"] = env("DJANGO_DATABASE_USER")
DATABASES["default"]["PASSWORD"] = env("DJANGO_DATABASE_PASSWORD")

# Require these AWS_SQS_ variables to be set explicitly. No defaults.
AWS_SQS_REGION = env("AWS_SQS_REGION")
AWS_SQS_ACCESS_KEY_ID = env("AWS_SQS_ACCESS_KEY_ID")
AWS_SQS_SECRET_ACCESS_KEY = env("AWS_SQS_SECRET_ACCESS_KEY")

# Require these HOUNDIGRADE_ variables to be set explicitly. No defaults.
HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME = env("HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME")
HOUNDIGRADE_ECS_CLUSTER_NAME = env("HOUNDIGRADE_ECS_CLUSTER_NAME")

AWS_NAME_PREFIX = env("AWS_NAME_PREFIX")
CELERY_BROKER_TRANSPORT_OPTIONS["queue_name_prefix"] = AWS_NAME_PREFIX
CLOUDTRAIL_NAME_PREFIX = AWS_NAME_PREFIX
QUEUE_EXCHANGE_NAME = None

STATIC_ROOT = env("DJANGO_STATIC_ROOT", default="/srv/cloudigrade/static/")

if env.bool("API_ENABLE_SENTRY", default=False):
    sentry_sdk.init(
        dsn=env("DJANGO_SENTRY_DSN"),
        environment=env("DJANGO_SENTRY_ENVIRONMENT"),
        release=env("DJANGO_SENTRY_RELEASE"),
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        integrations=[DjangoIntegration()],
        send_default_pii=True,
    )

# Specifically in production, this default should be False.
ENABLE_DATA_MANAGEMENT_FROM_KAFKA_SOURCES = env.bool(
    "ENABLE_DATA_MANAGEMENT_FROM_KAFKA_SOURCES",
    default=False,
)
