"""Helper utility module to wrap up common Azure Identity operations."""
from azure.identity import EnvironmentCredential
from django.conf import settings


def get_cloudigrade_credentials():
    """Fetch cloudigrade's own credentials stored in env vars."""
    return EnvironmentCredential()


def get_cloudigrade_subscription_id():
    """Fetch cloudigrade's own subscription id stored in settings."""
    return settings.AZURE_SUBSCRIPTION_ID
