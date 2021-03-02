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
from django.contrib.auth.models import User

from api import AWS_PROVIDER_STRING, AZURE_PROVIDER_STRING
from util import aws, misc

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

MIN_AWS_ACCOUNT_ID = 10 ** 10  # start "big" to better test handling of "big" numbers
MAX_AWS_ACCOUNT_ID = 10 ** 12 - 1


RH_IDENTITY_ORG_ADMIN = {
    "identity": {"account_number": "1337", "user": {"is_org_admin": True}}
}
RH_IDENTITY_NOT_ORG_ADMIN = {"identity": {"account_number": "1337"}}


def generate_dummy_aws_account_id():
    """Generate a dummy AWS AwsAccount ID for testing purposes."""
    return Decimal(random.randrange(MIN_AWS_ACCOUNT_ID, MAX_AWS_ACCOUNT_ID))


def generate_dummy_availability_zone(region=None):
    """Generate a dummy AWS availability zone for testing purposes."""
    if region is None:
        region = get_random_region()
    return "{}{}".format(region, random.choice(string.ascii_lowercase))


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


def generate_dummy_snapshot_id():
    """Generate a dummy AWS snapshot ID for testing purposes."""
    return "snap-{}".format(
        "".join(random.choice(string.hexdigits[:16]) for _ in range(17))
    )


def generate_dummy_volume_id():
    """Generate a dummy AWS volume ID for testing purposes."""
    return "vol-{}".format(
        "".join(random.choice(string.hexdigits[:16]) for _ in range(17))
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
        "name": _faker.bs()[:256],
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
        "tenant_id": uuid.uuid4(),
        "name": _faker.bs()[:256],
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


def generate_dummy_block_device_mapping(
    device_name=None,
    device_type="Ebs",
    attach_time=None,
    delete_on_termination=True,
    status="attached",
    volume_id=None,
):
    """
    Generate block device mapping to imitate part of 'describe instances' API response.

    All arguments are optional, and any not given will be randomly generated.

    Args:
        device_name (str): Optional known DeviceName value.
        device_type (str): Optional known device type key for nested status details.
        attach_time (str): Optional known AttachTime value.
        delete_on_termination (bool): Optional known DeleteOnTermination value.
        status (str): Optional known Status.
        volume_id (str): Optional known VolumeId value.

    Returns:
        dict: Well-formed BlockDeviceMapping data structure. Example:
        {
          "DeviceName": "/dev/xvda",
          "Ebs": {
            "AttachTime": "2020-10-08T19:07:23+00:00",
            "DeleteOnTermination": true,
            "Status": "attached",
            "VolumeId": "vol-06c61265cb97c1e1e"
          }
        }

    """
    if device_name is None:
        device_index = random.randint(0, 100)
        device_name = misc.generate_device_name(device_index)

    if attach_time is None:
        attach_time = misc.get_now().isoformat()

    if status is None:
        status = random.choice(["attaching", "attached", "detaching"])

    if volume_id is None:
        volume_id = generate_dummy_volume_id()

    mapping = {
        "DeviceName": device_name,
        device_type: {
            "AttachTime": attach_time,
            "DeleteOnTermination": delete_on_termination,
            "Status": status,
            "VolumeId": volume_id,
        },
    }
    return mapping


def generate_dummy_describe_instance(
    instance_id=None,
    image_id=None,
    subnet_id=None,
    state=None,
    instance_type=None,
    platform="",
    launch_time="",
    device_mappings=None,
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

    Returns:
        dict: Well-formed instance data structure.

    """
    if state is None:
        state = random.choice(list(aws.InstanceState))

    if image_id is None:
        image_id = generate_dummy_image_id()

    if instance_id is None:
        instance_id = generate_dummy_instance_id()

    if subnet_id is None:
        subnet_id = generate_dummy_subnet_id()

    if instance_type is None:
        instance_type = get_random_instance_type()

    if device_mappings is None:
        device_mappings = [
            generate_dummy_block_device_mapping(),
            generate_dummy_block_device_mapping(),
        ]

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
        "SubnetId": subnet_id,
    }
    return mock_instance


def generate_dummy_describe_image(
    image_id=None,
    owner_id=None,
    name=None,
    openshift=False,
    platform=None,
    architecture=None,
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
                "Key": aws.OPENSHIFT_TAG,
                "Value": aws.OPENSHIFT_TAG,
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


def generate_mock_image(image_id=None, encrypted=False, state=None):
    """
    Generate a mocked EC2 Image object.

    Args:
        image_id (str): The AMI image id.
        encrypted (bool): Is the image's device encrypted.
        state (str): The state of the image.

    Returns:
        Mock: A mock object with Image-like attributes.

    """
    root_device_name = "/dev/sda1"
    root_device_type = "ebs"
    volume_types = ("gp2", "io1", "st1", "sc1")
    block_device_mappings = [
        {
            "DeviceName": root_device_name,
            root_device_type.capitalize(): {
                "Encrypted": encrypted,
                "DeleteOnTermination": False,
                "SnapshotId": generate_dummy_snapshot_id(),
                "VolumeSize": random.randint(0, 10),
                "VolumeType": random.choice(volume_types),
            },
        }
    ]

    mock_image = Mock()
    mock_image.image_id = image_id
    mock_image.root_device_name = root_device_name
    mock_image.root_device_type = root_device_type
    mock_image.block_device_mappings = block_device_mappings
    mock_image.state = state
    return mock_image


def generate_mock_image_dict(image_id=None):
    """
    Generate a mocked EC2 image dict.

    Some of the AWS/boto3 APIs return a dict object like this instead of the
    EC2 Image object.

    Args:
        image_id (str): The AMI image id.

    Returns:
        Mock: A dict with attributes similar to what boto3 produces.

    """
    if image_id is None:
        image_id = generate_dummy_image_id()

    mock_image = {"ImageId": image_id}
    return mock_image


def generate_mock_snapshot(
    snapshot_id=None, encrypted=False, state=None, owner_id=None
):
    """
    Generate a mocked EC2 Image Snapshot object.

    Args:
        snapshot_id (str): The AWS snapshot id.
        encrypted (bool): Indicate if the image is encrypted.
        state (str): The AWS state of the snapshot.
        owner_id (str): The AWS account ID that owns this image.

    Returns:
        Mock: A mock object with Snapshot-like attributes.

    """
    if snapshot_id is None:
        snapshot_id = generate_dummy_snapshot_id()
    if state is None:
        state = "completed"

    mock_snapshot = Mock()
    mock_snapshot.snapshot_id = snapshot_id
    mock_snapshot.encrypted = encrypted
    mock_snapshot.state = state
    mock_snapshot.owner_id = owner_id
    return mock_snapshot


def generate_mock_volume(volume_id=None, snapshot_id=None, zone=None, state=None):
    """
    Generate a mocked EC2 EBS Volume object.

    Args:
        volume_id (str): Optional volume id.
        snapshot_id (str): Optional snapshot id.
        zone (str): Optional availability zone.

    Returns:
        Mock: A mock object with Volume-like attributes.

    """
    if volume_id is None:
        volume_id = generate_dummy_volume_id()
    if snapshot_id is None:
        snapshot_id = generate_dummy_snapshot_id()
    if zone is None:
        zone = generate_dummy_availability_zone()
    if state is None:
        state = random.choice(
            ("creating", "available", "in-use", "deleting", "deleted", "error")
        )

    mock_volume = Mock()
    mock_volume.id = volume_id
    mock_volume.snapshot_id = snapshot_id
    mock_volume.zone = zone
    mock_volume.state = state
    return mock_volume


def generate_mock_sqs_message(message_id, body, receipt_handle):
    """
    Generate a mocked SQS Message object.

    Args:
        message_id (str): The SQS message id.
        body (str): The message contents.
        receipt_handle (str): The SQS receipt handle.

    Returns:
        Mock: A mock object with Message-like attributes.

    """
    mock_message = Mock()
    mock_message.Id = message_id
    mock_message.ReceiptHandle = receipt_handle
    mock_message.body = body
    return mock_message


def utc_dt(*args, **kwargs):
    """Wrap datetime construction to force result to UTC.

    Returns:
        datetime.datetime

    """
    return datetime.datetime(*args, **kwargs).replace(tzinfo=tz.tzutc())


def generate_test_user(account_number=None, password=None, is_superuser=False):
    """
    Generate and save a user for testing.

    Args:
        account_number (str): optional account_number
        password (str): optional password
        is_superuser (bool): create as a superuser if True

    Returns:
        User: created Django auth User

    """
    if not account_number:
        account_number = _faker.random_int(min=100000, max=999999)
    user = User.objects.create_user(
        username=account_number,
        password=password,
        is_superuser=is_superuser,
    )
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
        user = User.objects.get(username=account_number)
        if password:
            user.set_password(password)
        user.is_superuser = is_superuser
        user.save()
    except User.DoesNotExist:
        user = generate_test_user(account_number, password, is_superuser)
    return user


def get_identity_auth_header(account_number="1337", is_org_admin=True):
    """
    Get an example identity auth header.

    Args:
        account_number (str): account number for the identity/insights account.
            defaults to "1337".
        is_org_admin (bool): should the identity be an org admin. defaults to True.

    Returns:
        str: base64 encoded identity header

    """
    header = copy.deepcopy(
        RH_IDENTITY_ORG_ADMIN if is_org_admin else RH_IDENTITY_NOT_ORG_ADMIN
    )
    header["identity"]["account_number"] = account_number
    return base64.b64encode(json.dumps(header).encode("utf-8"))


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
    auth_header = base64.b64encode(
        json.dumps({"identity": {"account_number": account_number}}).encode("utf-8")
    )
    headers = [
        ("x-rh-identity", auth_header),
    ]
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
    auth_header = base64.b64encode(
        json.dumps({"identity": {"account_number": account_number}}).encode("utf-8")
    )
    headers = [
        ("x-rh-identity", auth_header),
    ]
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
