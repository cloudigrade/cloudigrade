"""Helper functions for generating test data."""
import functools
import logging
import uuid
from unittest.mock import patch

import faker
from django.db.models import ForeignKey
from rest_framework.test import APIClient

from api import AWS_PROVIDER_STRING, AZURE_PROVIDER_STRING
from api.clouds.aws.models import AwsCloudAccount
from api.clouds.azure.models import AzureCloudAccount
from api.models import CloudAccount
from util import aws
from util.misc import get_now
from util.tests import helper

_faker = faker.Faker()
logger = logging.getLogger(__name__)


class SandboxedRestClient(object):
    """
    Very special REST client intended only for local sandbox testing.

    This client short-circuits some otherwise important behaviors so we don't
    make calls to the real public clouds when interacting with objects. These
    short-circuited behaviors all simulate "happy path" responses from the
    public clouds.

    This client can be useful for testing the general interaction and output of
    our APIs when we do not expect or need to override specific responses from
    the real public clouds.
    """

    def __init__(self, api_root="/api/cloudigrade/v2"):
        """Initialize the client."""
        self.client = APIClient()
        self.authenticated_user = None
        self.aws_account_verified = True
        self.aws_primary_account_id = int(helper.generate_dummy_aws_account_id())
        self.api_root = api_root

    def _call_api(self, verb, path, data=None, *args, **kwargs):
        """
        Make the simulated API call, optionally patching cloud interactions.

        The following objects are *always* patched to remove potential external calls
        so we remain more truly "sandboxed" for the duration of this request:

        - aws.verify_account_access is used in account creation
        - aws.sts.boto3 is used in account creation
        - api.serializers.verify_permissions is used in account creation
        - aws.delete_cloudtrail is used in account deletion
        - aws.get_session is used in account deletion
        - aws.sts._get_primary_account_id is used in sysconfig

        Returns:
            rest_framework.response.Response
        """
        with patch.object(aws, "verify_account_access") as mock_verify, patch(
            "api.clouds.aws.util.verify_permissions"
        ) as mock_verify_permissions, patch.object(aws.sts, "boto3"), patch.object(
            aws, "delete_cloudtrail"
        ), patch.object(
            aws, "get_session"
        ), patch.object(
            aws.sts, "_get_primary_account_id"
        ) as mock_get_primary_account_id:
            mock_verify.return_value = self.aws_account_verified, []
            mock_verify_permissions.return_value = True
            mock_get_primary_account_id.return_value = self.aws_primary_account_id
            response = getattr(self.client, verb)(path, data=data, *args, **kwargs)
        return response

    def __getattr__(self, item):
        """
        Get an appropriate RESTful API-calling method.

        If we want to customize any specific API's behavior, we can simply add
        a new method to this class following the "verb_noun" pattern. For
        example, "create_account" would handle POSTs to the account API.
        """
        try:
            verb, noun = item.split("_", 1)
            if verb == "list":
                verb = "get"
            elif verb == "create":
                verb = "post"
            return functools.partial(self.verb_noun, verb, noun)
        except Exception:
            raise AttributeError(
                f"'{self.__class__.__name__}' object " f"has no attribute '{item}'"
            )

    def _force_authenticate(self, user, credential_headers=None):
        """Force client authentication as the given user."""
        self.authenticated_user = user
        if credential_headers:
            self.client.credentials(**credential_headers)

    def verb_noun(
        self,
        verb,
        noun,
        noun_id=None,
        detail=None,
        data=None,
        api_root=None,
        *args,
        **kwargs,
    ):
        """Make a simulated REST API call for the given inputs."""
        if api_root is None:
            api_root = self.api_root
        if detail:
            path = f"{api_root}/{noun}/{noun_id}/{detail}/"
        elif noun_id:
            path = f"{api_root}/{noun}/{noun_id}/"
        elif verb == "report":
            path = f"{api_root}/report/{noun}/"
            verb = "get"
        else:
            path = f"{api_root}/{noun}/"
        return self._call_api(verb=verb, path=path, data=data, *args, **kwargs)


def generate_cloud_account(cloud_type=AWS_PROVIDER_STRING, **kwargs):
    """
    Generate a CloudAccount with linked provider-specific model instance for testing.

    Note:
        This function may be deprecated and removed in the near future since we will
        stop assuming AWS is a default as we improve support for additional cloud types.
        Please use a cloud-specific function (e.g. generate_cloud_account_aws,
        generate_cloud_account_azure) instead of this.

    Args:
        cloud_type (str): cloud provider type identifier
        **kwargs (dict): Optional additional kwargs to pass to generate_cloud_account.

    Returns:
        CloudAccount: The created CloudAccount instance.
    """
    if cloud_type == AWS_PROVIDER_STRING:
        return generate_cloud_account_aws(**kwargs)
    elif cloud_type == AZURE_PROVIDER_STRING:
        return generate_cloud_account_azure(**kwargs)
    else:
        raise NotImplementedError(f"Unsupported cloud_type '{cloud_type}'")


def generate_cloud_account_aws(
    arn=None,
    aws_account_id=None,
    created_at=None,
    **kwargs,
):
    """
    Generate a CloudAccount with linked AwsCloudAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        arn (str): Optional ARN.
        aws_account_id (str): Optional 12-digit AWS account ID.
        created_at (datetime): Optional creation datetime for this account.
        **kwargs (dict): Optional additional kwargs to pass to generate_cloud_account.

    Returns:
        CloudAccount: The created CloudAccount instance.
    """
    if arn is None:
        arn = helper.generate_dummy_arn(account_id=aws_account_id)

    if created_at is None:
        created_at = get_now()

    provider_cloud_account = AwsCloudAccount.objects.create(
        account_arn=arn,
        aws_account_id=aws.AwsArn(arn).account_id,
    )
    provider_cloud_account.created_at = created_at
    provider_cloud_account.save()

    return _generate_cloud_account(
        provider_cloud_account, created_at=created_at, **kwargs
    )


def generate_cloud_account_azure(
    azure_subscription_id=None,
    created_at=None,
    **kwargs,
):
    """
    Generate a CloudAccount with linked AzureCloudAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        azure_subscription_id (str): optional uuid str for azure subscription id
        created_at (datetime): Optional creation datetime for this account.
        **kwargs (dict): Optional additional kwargs to pass to generate_cloud_account.

    Returns:
        CloudAccount: The created CloudAccount instance.
    """
    if created_at is None:
        created_at = get_now()

    if azure_subscription_id is None:
        azure_subscription_id = uuid.uuid4()

    provider_cloud_account = AzureCloudAccount.objects.create(
        subscription_id=azure_subscription_id,
    )
    provider_cloud_account.created_at = created_at
    provider_cloud_account.save()

    return _generate_cloud_account(
        provider_cloud_account, created_at=created_at, **kwargs
    )


def _generate_cloud_account(
    provider_cloud_account,
    user=None,
    created_at=None,
    platform_authentication_id=None,
    platform_application_id=None,
    platform_application_is_paused=False,
    platform_source_id=None,
    is_enabled=True,
    enabled_at=None,
    missing_content_object=False,
):
    """
    Generate a CloudAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        provider_cloud_account (object): the provider-specific cloud account
            model instance (e.g. AwsCloudAccount, AzureCloudAccount) to be linked with
            the newly-created CloudAccount
        user (User): Optional Django auth User to be this account's owner.
        created_at (datetime): Optional creation datetime for this account.
        platform_authentication_id (int): Optional platform source authentication ID.
        platform_application_id (int): Optional platform source application ID.
        platform_source_id (int): Optional platform source source ID.
        is_enabled (bool): Optional should the account be enabled.
        enabled_at (datetime): Optional enabled datetime for this account.
        missing_content_object (bool): should the provider-specific cloud account
            (content_object) be missing; this is used to simulate unwanted edge cases in
            which the content_object is not correctly deleted with the CloudAccount.

    Returns:
        CloudAccount: The created Cloud Account.

    """
    if user is None:
        user = helper.generate_test_user()

    if created_at is None:
        created_at = get_now()

    if enabled_at is None:
        enabled_at = created_at

    if platform_authentication_id is None:
        platform_authentication_id = _faker.pyint()

    if platform_application_id is None:
        platform_application_id = _faker.pyint()

    if platform_source_id is None:
        platform_source_id = _faker.pyint()

    cloud_account = CloudAccount.objects.create(
        user=user,
        content_object=provider_cloud_account,
        platform_authentication_id=platform_authentication_id,
        platform_application_id=platform_application_id,
        platform_application_is_paused=platform_application_is_paused,
        platform_source_id=platform_source_id,
        is_enabled=is_enabled,
        enabled_at=enabled_at,
    )
    cloud_account.created_at = created_at
    cloud_account.save()

    if missing_content_object:
        provider_cloud_account_class = cloud_account.content_object.__class__
        content_object_queryset = provider_cloud_account_class.objects.filter(
            id=cloud_account.content_object.id
        )
        # Use _raw_delete so we don't trigger any signals or other model side-effects.
        content_object_queryset._raw_delete(content_object_queryset.db)
        # We need to get a fresh instance, not just use .refresh_from_db() because the
        # generic relation doesn't seem to update when calling .refresh_from_db() here.
        cloud_account = CloudAccount.objects.get(id=cloud_account.id)

    return cloud_account


class ModelStrTestMixin:
    """Mixin for test classes to add common assertion for str correctness."""

    def assertTypicalStrOutput(self, instance, exclude_field_names=None):
        """
        Assert instance's str output includes all relevant data.

        Our typical model string representation should look like:
            ClassName(field="value", other_field="value", related_model_id=1)
        """
        if exclude_field_names is None:
            exclude_field_names = ()
        output = str(instance)
        self.assertEqual(output, repr(instance))
        self.assertTrue(output.startswith(f"{instance.__class__.__name__}("))
        field_names = (
            field.name if not isinstance(field, ForeignKey) else f"{field.name}_id"
            for field in instance.__class__._meta.local_fields
            if field.name not in exclude_field_names
        )
        for field_name in field_names:
            self.assertIn(f"{field_name}=", output)
