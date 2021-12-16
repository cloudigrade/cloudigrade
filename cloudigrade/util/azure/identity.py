"""Helper utility module to wrap up common Azure Identity operations."""
from azure.identity import EnvironmentCredential
from azure.mgmt.resource import SubscriptionClient
from django.conf import settings


def get_cloudigrade_credentials():
    """Fetch cloudigrade's own credentials stored in env vars."""
    return EnvironmentCredential()


def get_cloudigrade_subscription_id():
    """Fetch cloudigrade's own subscription id stored in settings."""
    return settings.AZURE_SUBSCRIPTION_ID


def get_cloudigrade_available_subscriptions():
    """Fetch all azure subscription ids that cloudigrade has access to."""
    subs_client = SubscriptionClient(get_cloudigrade_credentials())
    subscriptions = []
    subscription_ids = []

    for sub in subs_client.subscriptions.list():
        subscriptions.append(sub.as_dict())

    for sub in subscriptions:
        subscription_ids.append(sub.get("subscription_id"))

    return subscription_ids
