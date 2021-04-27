"""Helper utility module to wrap up common AWS AutoScaling operations."""
import logging

import boto3
from django.utils.translation import gettext as _

from util.exceptions import AwsAutoScalingGroupNotFound

logger = logging.getLogger(__name__)


def describe_auto_scaling_group(name):
    """
    Describe the named Auto Scaling group.

    Args:
        name (str): Auto Scaling group name

    Returns:
        dict: Details describing the Auto Scaling group

    """
    autoscaling = boto3.client("autoscaling")
    groups = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[name], MaxRecords=1
    )["AutoScalingGroups"]
    if len(groups) == 0:
        raise AwsAutoScalingGroupNotFound(name)
    return groups[0]


def is_scaled_down(name):
    """
    Check if the Auto Scaling group is spun down with zero instances.

    Args:
        name: Auto Scaling group name

    Returns:
        tuple(bool, dict): the bool is True if group indicates zero size and
            zero instances, and the dict has the auto scaling group details
            that were described to make that determination.

    """
    auto_scaling_group = describe_auto_scaling_group(name)
    scaled_down = (
        auto_scaling_group["MinSize"] == 0
        and auto_scaling_group["MaxSize"] == 0
        and auto_scaling_group["DesiredCapacity"] == 0
        and len(auto_scaling_group["Instances"]) == 0
    )
    return scaled_down, auto_scaling_group


def set_scale(name, min_size, max_size, desired_capacity):
    """
    Set the Auto Scaling group to have exactly `count` instances.

    Args:
        name: Auto Scaling group name
        min_size (int): group min size
        max_size (int): group max size
        desired_capacity (int): group desired capacity

    Returns:
        dict: AWS response metadata

    """
    logger.info(
        _(
            "Updating %(name)s autoscaling to "
            "min %(min_size)s max %(max_size)s desired %(desired_capacity)s"
        ),
        {
            "name": name,
            "min_size": min_size,
            "max_size": max_size,
            "desired_capacity": desired_capacity,
        },
    )
    autoscaling = boto3.client("autoscaling")
    response = autoscaling.update_auto_scaling_group(
        AutoScalingGroupName=name,
        MinSize=min_size,
        MaxSize=max_size,
        DesiredCapacity=desired_capacity,
    )
    logger.info(
        "update_auto_scaling_group response: %(response)s", {"response": response}
    )
    return response


def scale_up(name):
    """
    Set the Auto Scaling group to have exactly 1 instance.

    Args:
        name: Auto Scaling group name

    Returns:
        dict: AWS response metadata

    """
    return set_scale(name, 1, 1, 1)


def scale_down(name):
    """
    Set the Auto Scaling group to have exactly 0 instance.

    Args:
        name: Auto Scaling group name

    Returns:
        dict: AWS response metadata

    """
    return set_scale(
        name,
        0,
        0,
        0,
    )
