"""Cloud-specific helpers to aid in cloud-agnostic report processing."""
from abc import ABC, abstractmethod

from django.db import models
from django.utils.translation import gettext as _

from account import CLOUD_PROVIDERS
from account.exceptions import InvalidCloudProviderError
from account.models import AwsAccount


def get_report_helper(cloud_provider, cloud_account_id):
    """
    Get a cloud-specific ReportHelper instance.

    Args:
        cloud_provider (str): The cloud provider
        cloud_account_id (str): The cloud-specific account ID

    Returns:
        ReportHelper: An instance of a cloud-specific ReportHelper child class.

    """
    if cloud_provider not in CLOUD_PROVIDERS:
        raise InvalidCloudProviderError(
            _('Unsupported cloud provider "{0}".').format(cloud_provider)
        )

    if cloud_provider == 'aws':
        return AwsReportHelper(cloud_account_id)

    raise NotImplementedError()


class ReportHelper(ABC):
    """Abstract base class for cloud-specific reporting helper functions."""

    def __init__(self, cloud_account_id):
        """
        Initialize a new ReportHelper instance.

        Args:
            cloud_account_id (str): The cloud-specific account ID
        """
        self.cloud_account_id = cloud_account_id

    @abstractmethod
    def assert_account_exists(self):
        """Assert that the cloud-specific account ID exists in cloudigrade."""

    @property
    @abstractmethod
    def instance_account_filter(self):
        """Get a Django query filter to restrict instances to this account."""

    @property
    @abstractmethod
    def event_account_filter(self):
        """Get a Django query filter to restrict events to this account."""

    @staticmethod
    @abstractmethod
    def get_event_product_identifier(event):
        """
        Get the cloud-specific product identifier for an event.

        Args:
            event (InstanceEvent): The invent to identify

        Returns:
            str: Some relatively unique string for grouping by product

        """

    @staticmethod
    @abstractmethod
    def get_event_instance_identifier(event):
        """
        Get the cloud-specific instance identifier for an event.

        Args:
            event (InstanceEvent): The invent to identify

        Returns:
            str: Some relatively unique string for grouping by instance

        """


class AwsReportHelper(ReportHelper):
    """Report helper for AWS."""

    def assert_account_exists(self):
        """Assert that the AWS account ID exists in cloudigrade."""
        if not AwsAccount.objects.filter(
                aws_account_id=self.cloud_account_id
        ).exists():
            raise AwsAccount.DoesNotExist()

    def instance_account_filter(self):
        """Get a Django query filter to restrict instances to this account."""
        return models.Q(
            account__awsaccount__aws_account_id=self.cloud_account_id
        )

    def event_account_filter(self):
        """Get a Django query filter to restrict events to this account."""
        return models.Q(
            instance__account__awsaccount__aws_account_id=self.cloud_account_id
        )

    @staticmethod
    def get_event_product_identifier(event):
        """Get the AWS instance's product identifier for an event."""
        return event.awsinstanceevent.product_identifier

    @staticmethod
    def get_event_instance_identifier(event):
        """Get the AWS EC2 instance ID for an event."""
        return event.instance.awsinstance.ec2_instance_id
