"""Helper functions for generating test data."""
import base64
import copy
import datetime
import json
import random
import uuid
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import Mock, patch

import faker
from dateutil import tz
from django.conf import settings

from api import AWS_PROVIDER_STRING, AZURE_PROVIDER_STRING
from api.models import User

_faker = faker.Faker()

MIN_AWS_ACCOUNT_ID = 10**10  # start "big" to better test handling of "big" numbers
MAX_AWS_ACCOUNT_ID = 10**12 - 1

RH_IDENTITY_ORG_ADMIN = {
    "identity": {"account_number": "1337", "user": {"is_org_admin": True}}
}
RH_IDENTITY_NOT_ORG_ADMIN = {"identity": {"account_number": "1337"}}

INTERNAL_RH_IDENTITY = {
    "identity": {
        "type": "Associate",
        "auth_type": "saml-auth",
        "associate": {"givenName": "John", "surname": "Doe"},
    }
}


def generate_dummy_aws_account_id():
    """Generate a dummy AWS AwsAccount ID for testing purposes."""
    return Decimal(random.randrange(MIN_AWS_ACCOUNT_ID, MAX_AWS_ACCOUNT_ID))


def generate_dummy_arn(
    account_id=None,
    region="",
    partition="aws",
    service="iam",
    resource_type="role",
    resource_separator="/",
    resource="role-for-cloudigrade",
):
    """
    Generate a dummy AWS ARN for testing purposes.

    Args:
        account_id (str): Optional account ID. Default is None. If None, an
            account ID will be randomly generated.
        region (str): Optional region. Default is ''.
        partition (str): Optional partition. Default is 'aws'.
        service (str): Optional partition. Default is 'iam'.
        resource_type (str): Optional resource type. Default is 'role'.
        resource_separator (str): A colon ':' or a forward-slash '/'
        resource (str): Optional resource name. If None, a resource will be
            randomly generated.

    Returns:
        str: A well-formed, randomized ARN.

    """
    if account_id is None:
        account_id = generate_dummy_aws_account_id()
    if resource is None:
        resource = _faker.name()
    arn = (
        f"arn:{partition}:{service}:{region}:{account_id}:"
        f"{resource_type}{resource_separator}{resource}"
    )
    return arn


def generate_dummy_aws_cloud_account_post_data():
    """
    Generate all post data needed for creating an AwsCloudAccount.

    Returns:
        dict with dummy data fully populated.
    """
    data = {
        "cloud_type": AWS_PROVIDER_STRING,
        "account_arn": generate_dummy_arn(),
        "platform_authentication_id": _faker.pyint(),
        "platform_application_id": _faker.pyint(),
        "platform_source_id": _faker.pyint(),
    }
    return data


def generate_dummy_azure_cloud_account_post_data():
    """
    Generate all post data needed for creating an AzureCloudAccount.

    Returns:
        dict with dummy data fully populated.
    """
    data = {
        "cloud_type": AZURE_PROVIDER_STRING,
        "subscription_id": uuid.uuid4(),
        "platform_authentication_id": _faker.pyint(),
        "platform_application_id": _faker.pyint(),
        "platform_source_id": _faker.pyint(),
    }
    return data


def generate_dummy_role():
    """Generate a dummy AWS role for testing purposes."""
    return {
        "Credentials": {
            "AccessKeyId": str(uuid.uuid4()),
            "SecretAccessKey": str(uuid.uuid4()),
            "SessionToken": str(uuid.uuid4()),
        },
        "foo": "bar",
    }


def utc_dt(*args, **kwargs):
    """Wrap datetime construction to force result to UTC.

    Returns:
        datetime.datetime

    """
    return datetime.datetime(*args, **kwargs).replace(tzinfo=tz.tzutc())


def generate_org_id():
    """Generate a random org_id."""
    return str(_faker.random_int(min=100000, max=999999))


def generate_test_user(
    account_number=None,
    password=None,
    is_superuser=False,
    date_joined=None,
    org_id=None,
    is_permanent=False,
):
    """
    Generate and save a user for testing.

    Args:
        account_number (str): optional account_number
        password (str): optional password
        is_superuser (bool): create as a superuser if True
        date_joined (datetime.datetime): optional when the user joined
        org_id (str): optional org_id
        is_permanent (bool): makes the new user permanent if True

    Returns:
        User: created Django auth User

    """
    if not account_number:
        account_number = str(_faker.random_int(min=100000, max=999999))
    kwargs = {
        "account_number": account_number,
        "password": password,
        "is_superuser": is_superuser,
        "is_permanent": is_permanent,
    }
    if org_id:
        kwargs["org_id"] = org_id
    if date_joined:
        kwargs["date_joined"] = date_joined
    user = User.objects.create_user(**kwargs)

    return user


def get_test_user(account_number=None, password=None, is_superuser=False):
    """
    Get user with updated password and superuser, creating if it doesn't exist.

    Args:
        account_number (str): optional account_number
        password (str): optional password
        is_superuser (bool): create (or update) as a superuser if True

    Returns:
        User: created Django auth User

    """
    try:
        user = User.objects.get(account_number=account_number)
        if password:
            user.set_password(password)
        user.is_superuser = is_superuser
        user.save()
    except User.DoesNotExist:
        user = generate_test_user(account_number, password, is_superuser)
    return user


def get_identity_auth_header(account_number="1337", is_org_admin=True, org_id=None):
    """
    Get an example identity auth header.

    Args:
        account_number (str): account number for the identity/insights account.
            defaults to "1337".
        is_org_admin (bool): should the identity be an org admin. defaults to True.
        org_id (str): Optionally set the org_id in the header.

    Returns:
        str: base64 encoded identity header

    """
    header = copy.deepcopy(
        RH_IDENTITY_ORG_ADMIN if is_org_admin else RH_IDENTITY_NOT_ORG_ADMIN
    )
    header["identity"]["account_number"] = account_number
    if org_id:
        header["identity"]["org_id"] = org_id
    return base64.b64encode(json.dumps(header).encode("utf-8"))


def get_internal_identity_auth_header():
    """
    Get an example internal SSO associate identity auth header.

    Returns:
        str: base64 encoded identity header

    """
    header = copy.deepcopy(INTERNAL_RH_IDENTITY)
    return base64.b64encode(json.dumps(header).encode("utf-8"))


def generate_sources_kafka_message_headers(account_number, event_type):
    """
    Generate headers for a typical Kafka message coming from sources-api.

    The contents of these headers are real strings, not encoded bytes. This simulates
    the headers *after* we have decoded them from the raw Kafka message object using
    extract_raw_sources_kafka_message.

    Args:
        account_number (str): the account number (e.g. "1234567")
        event_type (str): the event type (e.g. "Application.pause")

    Returns:
        list of tuples, each effectively a key and value representing a header
    """
    x_rh_identity_header = base64.b64encode(
        json.dumps(
            {
                "identity": {
                    "account_number": account_number,
                    "user": {"is_org_admin": True},
                }
            }
        ).encode("utf-8")
    ).decode("utf-8")
    headers = [
        ("event_type", event_type),
        ("x-rh-sources-account-number", account_number),
        ("x-rh-identity", x_rh_identity_header),
    ]
    return headers


def generate_sources_kafka_message_identity_headers(
    identity_account_number=None,
    identity_org_id=None,
    sources_account_number=None,
    sources_org_id=None,
    event_type=None,
):
    """
    Generate headers for a typical Kafka message coming from sources-api.

    The contents of these headers are real strings, not encoded bytes. This simulates
    the headers *after* we have decoded them from the raw Kafka message object using
    extract_raw_sources_kafka_message.

    Args:
        identity_account_number (str): the identity account number or None
        identity_org_id (str): the identity Org Id or None
        sources_account_number (str): x-rh-sources-account-number or None
        sources_org_id (str): the x-rh-sources-org-id or None
        event_type (str): the event type (e.g. "Application.pause")

    Returns:
        list of tuples, each effectively a key and value representing a header
    """
    identity_header = {
        "identity": {
            "user": {"is_org_admin": True},
        }
    }
    if identity_account_number:
        identity_header["identity"]["account_number"] = identity_account_number
    if identity_org_id:
        identity_header["identity"]["org_id"] = identity_org_id
    x_rh_identity_header = base64.b64encode(
        json.dumps(identity_header).encode("utf-8")
    ).decode("utf-8")
    headers = [
        ("x-rh-identity", x_rh_identity_header),
    ]
    if event_type:
        headers.append(("event_type", event_type))
    if sources_account_number:
        headers.append(("x-rh-sources-account-number", sources_account_number))
    if sources_org_id:
        headers.append(("x-rh-sources-org-id", sources_org_id))
    return headers


def generate_authentication_create_message_value(
    account_number="1337",
    username=None,
    platform_id=None,
    authentication_type=None,
    resource_id=None,
):
    """
    Generate a 'Authentication.create' message's value and header as if read from Kafka.

    Returns:
        message (dict): like Kafka message's value attribute'.
        headers (list): like Kafka headers.

    """
    if not username:
        username = _faker.user_name()
    if not platform_id:
        platform_id = _faker.pyint()
    if not resource_id:
        resource_id = _faker.pyint()
    if not authentication_type:
        authentication_type = random.choice(settings.SOURCES_CLOUDMETER_AUTHTYPES)
    message = {
        "username": username,
        "id": platform_id,
        "authtype": authentication_type,
        "resource_id": resource_id,
    }
    headers = generate_sources_kafka_message_headers(
        account_number, "Authentication.create"
    )
    return message, headers


def generate_applicationauthentication_create_message_value(
    account_number="1337",
    platform_id=None,
    application_id=None,
    authentication_id=None,
):
    """
    Generate an 'ApplicationAuthentication.create' message's value and header.

    Returns:
        message (dict): like Kafka message's value attribute'.
        headers (list): like Kafka headers.

    """
    if not platform_id:
        platform_id = _faker.pyint()

    message = {
        "id": platform_id,
        "application_id": application_id,
        "authentication_id": authentication_id,
    }
    headers = generate_sources_kafka_message_headers(
        account_number, "ApplicationAuthentication.create"
    )
    return message, headers


def generate_application_event_message_value(
    event_type, application_id, account_number
):
    """
    Generate an 'Application.{event_type}' message's extracted value and headers.

    Args:
        event_type (str): the Application-specific event type (e.g. "pause")
        application_id (str): the Application's id (e.g. "123")
        account_number (str): account number (e.g. "1234567")

    Returns:
        tuple(dict, list) representing the Kafka message's value and headers.

    """
    strftime_fmt = "%Y-%m-%dT%H:%M:%SZ"
    message = {
        "source_id": _faker.pyint(),
        "paused_at": _faker.date_time_this_decade().strftime(strftime_fmt),
        "id": application_id,
        "extra": {},
        "application_type_id": _faker.pyint(),
        "created_at": _faker.date_time_this_decade().strftime(strftime_fmt),
        "updated_at": _faker.date_time_this_decade().strftime(strftime_fmt),
        "availability_status": "available",
        "availability_status_error": "this is the last known status error string",
        "last_checked_at": _faker.date_time_this_decade().strftime(strftime_fmt),
        "last_available_at": None,
        "superkey_data": None,
        "tenant": account_number,
    }
    headers = generate_sources_kafka_message_headers(
        account_number, f"Authentication.{event_type}"
    )
    return message, headers


@contextmanager
def clouditardis(destination):
    """
    Context manager and decorator for time-traveling.

    If my calculations are correct, when this baby hits 88 miles per hour,
    you're going to see some serious tests.

    This time machine only works if the code you're calling is exclusively
    using `get_now` or `get_today` to find the current time or day. If your
    code is not using either of those functions to get the current time or day,
    please consider refactoring your code to use them!

    Args:
        destination (datetime.datetime): the destination datetime
    """
    with patch("util.misc.datetime") as mock_datetime, patch(
        "django.utils.timezone.now"
    ) as mock_django_now:
        mock_datetime.datetime.now.return_value = destination
        mock_django_now.return_value = destination
        yield


@contextmanager
def mock_signal_handler(signal, handler, sender):
    """Temporarily replace an existing Django signal handler with a Mock."""
    signal.disconnect(handler, sender=sender)
    mock_handler = Mock()
    signal.connect(mock_handler, sender=sender)
    yield mock_handler
    signal.disconnect(mock_handler, sender=sender)
    signal.connect(handler, sender=sender)
