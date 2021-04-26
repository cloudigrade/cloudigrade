"""Settings file meant for production like environments."""
import sentry_sdk
from boto3 import client
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *

IS_PRODUCTION = CLOUDIGRADE_ENVIRONMENT == "prod"

DJANGO_DEBUG = "False"

CLOUDIGRADE_ENVIRONMENT = env("CLOUDIGRADE_ENVIRONMENT")

HOUNDIGRADE_AWS_AVAILABILITY_ZONE = "us-east-1a"
HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME = (
    f"cloudigrade-ecs-asg-{CLOUDIGRADE_ENVIRONMENT}"
)
HOUNDIGRADE_ECS_CLUSTER_NAME = f"cloudigrade-ecs-{CLOUDIGRADE_ENVIRONMENT}"

# NAME PREFIX AND DERIVED VALUES NEED TO BE UPDATED
AWS_NAME_PREFIX = f"{CLOUDIGRADE_ENVIRONMENT}-"
HOUNDIGRADE_RESULTS_QUEUE_NAME = f"{AWS_NAME_PREFIX}inspection_results"
AWS_S3_BUCKET_NAME = f"{AWS_NAME_PREFIX}cloudigrade-trails"
CELERY_BROKER_TRANSPORT_OPTIONS["queue_name_prefix"] = AWS_NAME_PREFIX
CLOUDTRAIL_NAME_PREFIX = AWS_NAME_PREFIX
QUEUE_EXCHANGE_NAME = None

# Instead of calling _get_primary_account_id we are calling boto here directly
account_id = client("sts").get_caller_identity().get("Account")
AWS_CLOUDTRAIL_EVENT_URL = f"https://sqs.us-east-1.amazonaws.com/{account_id}/cloudigrade-cloudtrail-s3-{CLOUDIGRADE_ENVIRONMENT}"

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

STATIC_ROOT = env("DJANGO_STATIC_ROOT", default="/srv/cloudigrade/static/")

if env.bool("API_ENABLE_SENTRY", default=False):
    DJANGO_SENTRY_RELEASE = (
        CLOUDIGRADE_VERSION if CLOUDIGRADE_VERSION else env("DJANGO_SENTRY_RELEASE")
    )

    sentry_sdk.init(
        dsn=env("DJANGO_SENTRY_DSN"),
        environment=env("DJANGO_SENTRY_ENVIRONMENT"),
        release=DJANGO_SENTRY_RELEASE,
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        integrations=[DjangoIntegration()],
        send_default_pii=True,
    )

# Specifically in production, this default should be False.
SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA = env.bool(
    "SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA",
    default=False,
)
