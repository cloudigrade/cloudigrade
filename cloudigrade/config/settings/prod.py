"""Settings file meant for production like environments."""
import sentry_sdk
from boto3 import client
from sentry_sdk.integrations.django import DjangoIntegration

from app_common_python import isClowderEnabled
from app_common_python import LoadedConfig as clowder_cfg

from .base import *

IS_PRODUCTION = CLOUDIGRADE_ENVIRONMENT == "prod"

DJANGO_DEBUG = "False"

# CLOUDIGRADE_ENVIRONMENT may have been loaded in base.py, but if not present, it would
# have fallen back to generic defaults. However, in prod, we *require* that it be set
# explicitly. By reloading here *without* a default, we halt app startup if not present.
CLOUDIGRADE_ENVIRONMENT = env("CLOUDIGRADE_ENVIRONMENT")

# Note: Why is HOUNDIGRADE_AWS_AVAILABILITY_ZONE special here?
# Originally, we manually configured houndigrade to always use this AZ, and we preserved
# that decision when we built its related Ansible playbook role. This could be made
# configurable in both places, but we're leaving it static for now because this should
# change when we (eventually) replace houndigrade's use of ECS with cloud-init.
HOUNDIGRADE_AWS_AVAILABILITY_ZONE = "us-east-1a"

# Instead of calling util.aws.sts._get_primary_account_id,
# we use boto here directly to avoid a potential import loop.
account_id = client("sts").get_caller_identity().get("Account")
AWS_CLOUDTRAIL_EVENT_URL = f"https://sqs.us-east-1.amazonaws.com/{account_id}/cloudigrade-cloudtrail-s3-{CLOUDIGRADE_ENVIRONMENT}"

SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

if isClowderEnabled():
    DATABASES["default"]["NAME"] = clowder_cfg.database.name
    DATABASES["default"]["HOST"] = clowder_cfg.database.hostname
    DATABASES["default"]["USER"] = clowder_cfg.database.username
    DATABASES["default"]["PASSWORD"] = clowder_cfg.database.password
else:
    DATABASES["default"]["NAME"] = env("DJANGO_DATABASE_NAME")
    DATABASES["default"]["HOST"] = env("DJANGO_DATABASE_HOST")
    DATABASES["default"]["USER"] = env("DJANGO_DATABASE_USER")
    DATABASES["default"]["PASSWORD"] = env("DJANGO_DATABASE_PASSWORD")

# Require these AWS_SQS_ variables to be set explicitly. No defaults.
AWS_SQS_REGION = env("AWS_SQS_REGION")
AWS_SQS_ACCESS_KEY_ID = env("AWS_SQS_ACCESS_KEY_ID")
AWS_SQS_SECRET_ACCESS_KEY = env("AWS_SQS_SECRET_ACCESS_KEY")

# Azure Settings
AZURE_CLIENT_ID = env("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = env("AZURE_CLIENT_SECRET")
AZURE_SUBSCRIPTION_ID = env("AZURE_SUBSCRIPTION_ID")
AZURE_TENANT_ID = env("AZURE_TENANT_ID")

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
