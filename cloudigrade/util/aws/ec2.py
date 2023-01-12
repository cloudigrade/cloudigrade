"""Helper utility module to wrap up common AWS EC2 operations."""
import enum
import logging

from django.utils.translation import gettext as _

from util.aws.helper import get_regions

logger = logging.getLogger(__name__)


class InstanceState(enum.Enum):
    """
    Enumeration of EC2 instance state codes.

    See also:
        https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_InstanceState.html

    """

    pending = 0
    running = 16
    shutting_down = 32
    terminated = 48
    stopping = 64
    stopped = 80

    @classmethod
    def is_running(cls, code):
        """
        Check if the given code is effectively a running state.

        Args:
            code (int): The code from an EC2 AwsInstance state.

        Returns:
            bool: True if we consider the instance to be running else False.

        """
        return code == cls.running.value


def describe_instances_everywhere(session):
    """
    Describe all EC2 instances visible to the given ARN in every known region.

    Note:
        When we collect and return the results of the AWS describe calls, we now
        specifically exclude instances that have the terminated state. Although we
        should be able to extract useful data from them, in our integration tests when
        we are rapidly creating and terminating EC2 instances, it has been confusing to
        see data from terminated instances from a previous test affect later tests.
        There does not appear to be a convenient way to handle this in those tests since
        AWS also takes an unknown length of time to actually remove terminated
        instances. So, we are "solving" this problem here by unilaterally ignoring them.

    Args:
        session (boto3.Session): A temporary session tied to a customer account

    Returns:
        dict: Lists of instance IDs keyed by region where they were found.

    """
    running_instances = {}

    for region_name in get_regions(session):
        ec2 = session.client("ec2", region_name=region_name)
        logger.debug(_("Describing instances in %s"), region_name)
        instances = ec2.describe_instances()
        running_instances[region_name] = list()
        for reservation in instances.get("Reservations", []):
            running_instances[region_name].extend(
                [
                    instance
                    for instance in reservation.get("Instances", [])
                    if instance.get("State", {}).get("Code", None)
                    != InstanceState.terminated.value
                ]
            )

    return running_instances


def describe_instances(session, instance_ids, source_region):
    """
    Describe multiple AWS EC2 Instances.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        instance_ids (list[str]): The EC2 instance IDs
        source_region (str): The region the instances are running in

    Returns:
        list(dict): List of dicts that describe the requested instances

    """
    ec2 = session.client("ec2", region_name=source_region)
    results = ec2.describe_instances(InstanceIds=list(instance_ids))
    instances = dict()
    for reservation in results.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            instances[instance["InstanceId"]] = instance
    return instances


def describe_images(session, image_ids, source_region):
    """
    Describe multiple AWS Amazon Machine Images.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        image_id (list[str]): The AMI IDs
        source_region (str): The region the images reside in

    Returns:
        list(dict): List of dicts that describe the requested AMIs

    """
    ec2 = session.client("ec2", region_name=source_region)
    return ec2.describe_images(ImageIds=list(image_ids))["Images"]


def describe_image(session, image_id, source_region):
    """
    Describe a single AWS Amazon Machine Image.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        image_id (list[str]): The AMI ID
        source_region (str): The region the image resides in

    Returns:
        dict: the described AMI

    """
    return describe_images(session, [image_id], source_region)[0]


def is_windows(aws_data):
    """
    Check to see if the instance or image has the windows platform set.

    Args:
        instance_data (object): Can be a dict, ec2.instance, or ec2.image
            object depending what the source of the data was. Describes the
            ec2 instance or image.

    Returns:
        bool: True if it appears to be windows, else False.

    """
    return (
        aws_data.get("Platform", "").lower() == "windows"
        if isinstance(aws_data, dict)
        else getattr(aws_data, "platform", None) == "windows"
    )
