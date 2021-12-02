"""Settings file meant for local development."""
from boto3 import client

from .base import *

DEBUG = env.bool("DJANGO_DEBUG", default=True)
SECRET_KEY = env("DJANGO_SECRET_KEY", default="local")
if env.bool("ENABLE_DJANGO_EXTENSIONS", default=False):
    INSTALLED_APPS = INSTALLED_APPS + ["django_extensions"]

# Instead of calling util.aws.sts._get_primary_account_id,
# we use boto here directly to avoid a potential import loop.
account_id = client("sts").get_caller_identity().get("Account")
AWS_CLOUDTRAIL_EVENT_URL = (
    f"https://sqs.us-east-1.amazonaws.com/"
    f"{account_id}/{CLOUDIGRADE_ENVIRONMENT}-cloudigrade-cloudtrail-s3"
)
