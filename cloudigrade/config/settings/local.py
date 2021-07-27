"""Settings file meant for local development."""
from boto3 import client
from .base import *

DEBUG = env.bool("DJANGO_DEBUG", default=True)
SECRET_KEY = env("DJANGO_SECRET_KEY", default="local")
INSTALLED_APPS = INSTALLED_APPS + ["django_extensions"]

# Instead of calling util.aws.sts._get_primary_account_id,
# we use boto here directly to avoid a potential import loop.
account_id = client("sts").get_caller_identity().get("Account")
AWS_CLOUDTRAIL_EVENT_URL = f"https://sqs.us-east-1.amazonaws.com/{account_id}/cloudigrade-cloudtrail-s3-{CLOUDIGRADE_ENVIRONMENT}"

# Only for local development allow setting Celery's "eager" option.
# Setting this to "True" means Celery will never enqueue task messages for processing.
# Instead it will always act as though the task function was called *directly*.
# See also Celery docs:
# https://docs.celeryproject.org/en/stable/userguide/configuration.html#std-setting-task_always_eager
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
