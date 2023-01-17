"""Helper functions for generating test data."""
import base64
import copy
import datetime
import json
import random
import string
import uuid
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import Mock, patch

import faker
from dateutil import tz
from django.conf import settings

from api import AWS_PROVIDER_STRING, AZURE_PROVIDER_STRING
from api.models import User
from util import OPENSHIFT_TAG, aws

_faker = faker.Faker()

SOME_AWS_REGIONS = (
    "ap-northeast-1",
    "ca-central-1",
    "eu-west-1",
    "us-east-1",
    "us-east-2",
)

SOME_EC2_INSTANCE_TYPES = {
    "c5.xlarge": {
        "memory": 8192,
        "vcpu": 4,
        "json_definition": {
            "InstanceType": "c5.xlarge",
            "MemoryInfo": {"SizeInMiB": 8192},
            "ProcessorInfo": {
                "SupportedArchitectures": ["x86_64"],
                "SustainedClockSpeedInGhz": 3.4,
            },
            "VCpuInfo": {
                "DefaultCores": 2,
                "DefaultThreadsPerCore": 2,
                "DefaultVCpus": 4,
                "ValidCores": [2],
                "ValidThreadsPerCore": [1, 2],
            },
        },
    },
    "m5.24xlarge": {
        "memory": 393216,
        "vcpu": 96,
        "json_definition": {
            "InstanceType": "m5.24xlarge",
            "ProcessorInfo": {
                "SupportedArchitectures": ["x86_64"],
                "SustainedClockSpeedInGhz": 3.1,
            },
            "VCpuInfo": {
                "DefaultVCpus": 96,
                "DefaultCores": 48,
                "DefaultThreadsPerCore": 2,
                "ValidCores": [
                    4,
                    6,
                    8,
                    10,
                    12,
                    14,
                    16,
                    18,
                    20,
                    22,
                    24,
                    26,
                    28,
                    30,
                    32,
                    34,
                    36,
                    38,
                    40,
                    42,
                    44,
                    46,
                    48,
                ],
                "ValidThreadsPerCore": [1, 2],
            },
            "MemoryInfo": {"SizeInMiB": 393216},
        },
    },
    "r4.large": {
        "memory": 15616,
        "vcpu": 2,
        "json_definition": {
            "InstanceType": "r4.large",
            "ProcessorInfo": {
                "SupportedArchitectures": ["x86_64"],
                "SustainedClockSpeedInGhz": 2.3,
            },
            "VCpuInfo": {
                "DefaultVCpus": 2,
                "DefaultCores": 1,
                "DefaultThreadsPerCore": 2,
                "ValidCores": [1],
                "ValidThreadsPerCore": [1, 2],
            },
            "MemoryInfo": {"SizeInMiB": 15616},
        },
    },
    "t2.large": {
        "memory": 8192,
        "vcpu": 2,
        "json_definition": {
            "InstanceType": "t2.large",
            "ProcessorInfo": {
                "SupportedArchitectures": ["x86_64"],
                "SustainedClockSpeedInGhz": 2.3,
            },
            "VCpuInfo": {
                "DefaultVCpus": 2,
                "DefaultCores": 2,
                "DefaultThreadsPerCore": 1,
                "ValidCores": [1, 2],
                "ValidThreadsPerCore": [1],
            },
            "MemoryInfo": {"SizeInMiB": 8192},
        },
    },
    "t2.medium": {
        "memory": 4096,
        "vcpu": 2,
        "json_definition": {
            "InstanceType": "t2.medium",
            "ProcessorInfo": {
                "SupportedArchitectures": ["i386", "x86_64"],
                "SustainedClockSpeedInGhz": 2.3,
            },
            "VCpuInfo": {
                "DefaultVCpus": 2,
                "DefaultCores": 2,
                "DefaultThreadsPerCore": 1,
                "ValidCores": [1, 2],
                "ValidThreadsPerCore": [1],
            },
            "MemoryInfo": {"SizeInMiB": 4096},
        },
    },
    "t2.micro": {
        "memory": 1024,
        "vcpu": 1,
        "json_definition": {
            "InstanceType": "t2.micro",
            "ProcessorInfo": {
                "SupportedArchitectures": ["i386", "x86_64"],
                "SustainedClockSpeedInGhz": 2.5,
            },
            "VCpuInfo": {
                "DefaultVCpus": 1,
                "DefaultCores": 1,
                "DefaultThreadsPerCore": 1,
                "ValidCores": [1],
                "ValidThreadsPerCore": [1],
            },
            "MemoryInfo": {"SizeInMiB": 1024},
        },
    },
    "t2.nano": {
        "memory": 512,
        "vcpu": 1,
        "json_definition": {
            "InstanceType": "t2.nano",
            "ProcessorInfo": {
                "SupportedArchitectures": ["i386", "x86_64"],
                "SustainedClockSpeedInGhz": 2.4,
            },
            "VCpuInfo": {
                "DefaultVCpus": 1,
                "DefaultCores": 1,
                "DefaultThreadsPerCore": 1,
                "ValidCores": [1],
                "ValidThreadsPerCore": [1],
            },
            "MemoryInfo": {"SizeInMiB": 512},
        },
    },
    "t2.small": {
        "memory": 2048,
        "vcpu": 1,
        "json_definition": {
            "InstanceType": "t2.small",
            "ProcessorInfo": {
                "SupportedArchitectures": ["i386", "x86_64"],
                "SustainedClockSpeedInGhz": 2.5,
            },
            "VCpuInfo": {
                "DefaultVCpus": 1,
                "DefaultCores": 1,
                "DefaultThreadsPerCore": 1,
                "ValidCores": [1],
                "ValidThreadsPerCore": [1],
            },
            "MemoryInfo": {"SizeInMiB": 2048},
        },
    },
    "t2.xlarge": {
        "memory": 16384,
        "vcpu": 4,
        "json_definition": {
            "InstanceType": "t2.xlarge",
            "ProcessorInfo": {
                "SupportedArchitectures": ["x86_64"],
                "SustainedClockSpeedInGhz": 2.3,
            },
            "VCpuInfo": {
                "DefaultVCpus": 4,
                "DefaultCores": 4,
                "DefaultThreadsPerCore": 1,
                "ValidCores": [1, 2, 3, 4],
                "ValidThreadsPerCore": [1],
            },
            "MemoryInfo": {"SizeInMiB": 16384},
        },
    },
    "x1e.32xlarge": {
        "memory": 3997696,
        "vcpu": 128,
        "json_definition": {
            "InstanceType": "x1e.32xlarge",
            "ProcessorInfo": {
                "SupportedArchitectures": ["x86_64"],
                "SustainedClockSpeedInGhz": 2.3,
            },
            "VCpuInfo": {
                "DefaultVCpus": 128,
                "DefaultCores": 64,
                "DefaultThreadsPerCore": 2,
                "ValidCores": [
                    4,
                    8,
                    12,
                    16,
                    20,
                    24,
                    28,
                    32,
                    36,
                    40,
                    44,
                    48,
                    52,
                    56,
                    60,
                    64,
                ],
                "ValidThreadsPerCore": [1, 2],
            },
            "MemoryInfo": {"SizeInMiB": 3997696},
        },
    },
}

SOME_AZURE_REGIONS = (
    "East US",
    "East US 2",
    "South Central US",
    "North Europe",
    "EAST US 2 EUAP",
)

SOME_AZURE_INSTANCE_TYPES = {
    "Standard_B4ms": {"memory": 16, "vcpu": 4},
    "Standard_A1_v2": {"memory": 2, "vcpu": 1},
    "Standard_D96a_v4": {"memory": 384, "vcpu": 96},
    "Standard_D16as_v4": {"memory": 64, "vcpu": 16},
    "Standard_D64d_v4": {"memory": 256, "vcpu": 64},
}

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


def generate_dummy_instance_id():
    """Generate a dummy AWS EC2 instance ID for testing purposes."""
    return "i-{}".format(
        "".join(random.choice(string.hexdigits[:16]) for _ in range(17))
    )


def generate_dummy_azure_instance_id():
    """Generate a dummy Azure instance ID for testing purposes."""
    return (
        f"/subscriptions/{uuid.uuid4()}/resourceGroups/{_faker.word()}"
        f"/providers/Microsoft.Compute/virtualMachines/{_faker.word()}"
    )


def generate_dummy_subnet_id():
    """Generate a dummy AWS EC2 subnet ID for testing purposes."""
    return "subnet-{}".format(
        "".join(random.choice(string.hexdigits[:16]) for _ in range(8))
    )


def generate_dummy_image_id():
    """Generate a dummy AWS image ID for testing purposes."""
    return "ami-{}".format(
        "".join(random.choice(string.hexdigits[:16]) for _ in range(8))
    )


def generate_dummy_azure_image_id():
    """Generate a dummy AWS image ID for testing purposes."""
    return (
        f"/subscriptions/{uuid.uuid4()}/resourceGroups/{_faker.word()}"
        f"/providers/Microsoft.Compute/images/{_faker.word()}"
    )


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


def get_random_instance_type(avoid=None, cloud_type=AWS_PROVIDER_STRING):
    """
    Get a randomly selected cloud provider instance type. Defaults to AWS.

    Args:
        avoid (str): optional specific instance type to avoid

    Returns:
        str: AWS EC2 instance type

    """
    if cloud_type == AZURE_PROVIDER_STRING:
        instance_types = set(SOME_AZURE_INSTANCE_TYPES.keys())
    else:
        instance_types = set(SOME_EC2_INSTANCE_TYPES.keys())
    instance_types.discard(avoid)
    instance_type = random.choice(tuple(instance_types))
    return instance_type


def get_random_region(cloud_type=AWS_PROVIDER_STRING):
    """
    Get a randomly selected region. Default to AWS.

    Returns:
        str: A cloud provider region name

    """
    if cloud_type == AZURE_PROVIDER_STRING:
        return random.choice(SOME_AZURE_REGIONS)
    else:
        return random.choice(SOME_AWS_REGIONS)


def generate_dummy_describe_instance(
    instance_id=None,
    image_id=None,
    subnet_id=None,
    state=None,
    instance_type=None,
    platform="",
    launch_time="",
    device_mappings=None,
    no_subnet=False,
):
    """
    Generate dummy instance to imitate 'describe instances' API response.

    All arguments are optional, and any not given will be randomly generated.

    Args:
        instance_id (str): Optional EC2 AwsInstance ID.
        image_id (str): Optional AMI ID.
        subnet_id (str): Optional Subnet ID.
        state (aws.InstanceState): Optional known state of the AwsInstance.
        instance_type (str): Optional known EC2 type of AwsInstance.
        platform (str): Optional known Platform value.
        launch_time (str): Optional known LaunchTime value.
        device_mappings (list): Optional known BlockDeviceMappings value
        no_subnet (bool): Optional bool to allow missing subnet value.

    Returns:
        dict: Well-formed instance data structure.

    """
    if state is None:
        state = random.choice(list(aws.InstanceState))

    if image_id is None:
        image_id = generate_dummy_image_id()

    if instance_id is None:
        instance_id = generate_dummy_instance_id()

    if subnet_id is None and not no_subnet:
        subnet_id = generate_dummy_subnet_id()

    if instance_type is None:
        instance_type = get_random_instance_type()

    if device_mappings is None:
        device_mappings = [dict(), dict()]

    mock_instance = {
        "BlockDeviceMappings": device_mappings,
        "ImageId": image_id,
        "InstanceId": instance_id,
        "InstanceType": instance_type,
        "LaunchTime": launch_time,
        "Platform": platform,
        "State": {
            "Code": state.value,
            "Name": state.name,
        },
    }
    if not no_subnet:
        mock_instance["SubnetId"] = subnet_id
    return mock_instance


def generate_dummy_describe_image(
    image_id=None,
    owner_id=None,
    name=None,
    openshift=False,
    platform=None,
    architecture=None,
    generate_marketplace_product_code=False,
):
    """
    Generate dummy image to imitate 'describe images' API response.

    Optional arguments not given may be randomly generated.

    Args:
        image_id (str): Optional AMI ID.
        owner_id (str): Optional AWS Account ID.
        name (str): Optional image name.
        openshift (bool): Optional indicator for openshift.
        platform (str): Optional known Platform value.
        architecture (str): Optional known Architecture value.
        generate_marketplace_product_code (bool): Optional should the generated image
            also have a marketplace-type product code.

    Returns:
        dict: Well-formed image data structure.

    """
    if image_id is None:
        image_id = generate_dummy_image_id()

    if owner_id is None:
        owner_id = Decimal(generate_dummy_aws_account_id())

    if name is None:
        name = _faker.bs()

    tags = []
    if openshift:
        tags.append(
            {
                "Key": OPENSHIFT_TAG,
                "Value": OPENSHIFT_TAG,
            }
        )

    mock_image = {
        "ImageId": image_id,
        "OwnerId": owner_id,
        "Name": name,
        "Tags": tags,
    }
    if platform is not None:
        mock_image["Platform"] = platform
    if architecture is not None:
        mock_image["Architecture"] = architecture

    if generate_marketplace_product_code:
        mock_image["ProductCodes"] = [
            {
                "ProductCodeId": str(uuid.uuid4()),
                "ProductCodeType": aws.AWS_PRODUCT_CODE_TYPE_MARKETPLACE,
            }
        ]

    return mock_image


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


def generate_vm_data(
    id=None,
    vm_id=None,
    architecture=None,
    azure_marketplace_image=False,
    name=None,
    openshift_detected=False,
    image_sku=None,
    inspection_json=None,
    is_encrypted=False,
    region=None,
    resourceGroup=None,
    rhel_detected_by_tag=False,
    running=False,
    subscription=None,
    tags=None,
    vm_size=None,
):
    """Generate a dict for a single discovered azure vm."""
    vm_data = {}
    subscription = subscription or _faker.uuid4()
    vm_data["image_sku"] = image_sku or _faker.slug()
    vm_data["name"] = name or _faker.slug()
    vm_data["resourceGroup"] = resourceGroup or _faker.slug()
    vm_data["id"] = (
        "/subscriptions/{}"
        "/resourceGroups/{}"
        "/providers/Microsoft.Computer"
        "/virtualMachines/{}"
    ).format(subscription, vm_data["resourceGroup"], vm_data["name"])
    vm_data["vm_id"] = vm_id or _faker.uuid4()
    vm_data["azure_marketplace_image"] = azure_marketplace_image
    vm_data["region"] = region or get_random_region(cloud_type=AZURE_PROVIDER_STRING)
    vm_data["inspection_json"] = inspection_json or {}
    vm_data["is_encrypted"] = is_encrypted
    vm_data["running"] = running
    vm_data["openshift_detected"] = openshift_detected
    vm_data["rhel_detected_by_tag"] = rhel_detected_by_tag
    vm_data["architecture"] = architecture or "x64"
    vm_data["tags"] = tags or {}
    vm_data["vm_size"] = vm_size or get_random_instance_type(
        cloud_type=AZURE_PROVIDER_STRING
    )
    return vm_data


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
