"""Utility functions for AWS models and use cases."""

import logging

from botocore.exceptions import ClientError
from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import error_codes
from api.clouds.aws.models import AwsCloudAccount
from api.models import CloudAccount
from util import aws
from util.exceptions import InvalidArn

logger = logging.getLogger(__name__)


def verify_permissions(customer_role_arn, external_id):  # noqa: C901
    """
    Verify AWS permissions.

    This function may raise ValidationError if certain verification steps fail.

    Args:
        customer_role_arn (str): ARN to access the customer's AWS account
        external_id (str): External Id supplied to us by sources
    Note:
        This function also has the side effect of notifying sources and updating the
        application status to unavailable if we cannot complete processing normally.

    Returns:
        boolean True if customer AWS account is appropriately accessible.

    """
    aws_account_id = aws.AwsArn(customer_role_arn).account_id
    arn_str = str(customer_role_arn)

    access_verified = False

    try:
        cloud_account = CloudAccount.objects.get(
            aws_cloud_account__aws_account_id=aws_account_id
        )
    except CloudAccount.DoesNotExist:
        # Failure to get CloudAccount means it was removed before this function started.
        logger.warning(
            "Cannot verify permissions because CloudAccount does not exist for %(arn)s",
            {"arn": customer_role_arn},
        )
        # Alas, we can't notify sources here since we don't have the CloudAccount which
        # is what has the required platform_application_id.
        return False

    # Get the username immediately from the related user in case the user is deleted
    # while we are verifying access; we'll need it later
    # in order to notify sources of our error.
    account_number = cloud_account.user.account_number
    org_id = cloud_account.user.org_id

    try:
        session = aws.get_session(arn_str, external_id)
        access_verified, failed_actions = aws.verify_account_access(session)
        if not access_verified:
            for action in failed_actions:
                logger.info(
                    "Policy action %(action)s failed in verification for via %(arn)s",
                    {"action": action, "arn": arn_str},
                )
            error_code = error_codes.CG3003
            error_code.notify(
                account_number, org_id, cloud_account.platform_application_id
            )
    except ClientError as error:
        # Generally only raised when we don't have access to the AWS account.
        client_error_code = error.response.get("Error", {}).get("Code")
        if client_error_code not in aws.COMMON_AWS_ACCESS_DENIED_ERROR_CODES:
            # We only expect to get those types of access errors, all of which basically
            # mean the permissions were removed by the time we made a call the AWS.
            # If we get any *other* kind of error, we need to alert ourselves about it!
            logger.error(
                "Unexpected AWS ClientError '%(code)s' in verify_permissions.",
                {"code": client_error_code},
            )
        # Irrespective of error code, log and notify sources about the access error.
        error_code = error_codes.CG3002
        error_code.log_internal_message(
            logger, {"cloud_account_id": cloud_account.id, "exception": error}
        )
        error_code.notify(account_number, org_id, cloud_account.platform_application_id)
    except Exception as error:
        # It's unclear what could cause any other kind of exception to be raised here,
        # but we must handle anything, log/alert ourselves, and notify sources.
        logger.exception(
            "Unexpected exception in verify_permissions: %(error)s", {"error": error}
        )
        error_code = error_codes.CG3000  # TODO Consider a new error code?
        error_code.notify(account_number, org_id, cloud_account.platform_application_id)

    return access_verified


def create_aws_cloud_account(
    user,
    customer_role_arn,
    platform_authentication_id,
    platform_application_id,
    platform_source_id,
    external_id,
):
    """
    Create AwsCloudAccount for the customer user.

    This function may raise ValidationError if certain verification steps fail.

    We call CloudAccount.enable after creating it, and that effectively verifies AWS
    permission. If that fails, we must abort this creation.
    That is why we put almost everything here in a transaction.atomic() context.

    Args:
        user (api.User): user to own the CloudAccount
        customer_role_arn (str): ARN to access the customer's AWS account
        platform_authentication_id (str): Platform Sources' Authentication object id
        platform_application_id (str): Platform Sources' Application object id
        platform_source_id (str): Platform Sources' Source object id

    Returns:
        CloudAccount the created cloud account.

    """
    logger.info(
        _(
            "Creating an AwsCloudAccount. "
            "user=%(user)s, "
            "customer_role_arn=%(customer_role_arn)s, "
            "platform_authentication_id=%(platform_authentication_id)s, "
            "platform_application_id=%(platform_application_id)s, "
            "platform_source_id=%(platform_source_id)s"
            "external_id=%(external_id)s"
        ),
        {
            "user": user.account_number,
            "customer_role_arn": customer_role_arn,
            "platform_authentication_id": platform_authentication_id,
            "platform_application_id": platform_application_id,
            "platform_source_id": platform_source_id,
            "external_id": external_id,
        },
    )
    aws_account_id = aws.AwsArn(customer_role_arn).account_id
    arn_str = str(customer_role_arn)

    with transaction.atomic():
        # Verify that no AwsCloudAccount already exists with the same ARN.
        if AwsCloudAccount.objects.filter(account_arn=arn_str).exists():
            error_code = error_codes.CG1001
            error_code.notify(user.account_number, user.org_id, platform_application_id)
            raise ValidationError({"account_arn": error_code.get_message()})

        # Verify that no AwsCloudAccount already exists with the same AWS Account ID.
        if AwsCloudAccount.objects.filter(aws_account_id=aws_account_id).exists():
            error_code = error_codes.CG1002
            error_code.notify(user.account_number, user.org_id, platform_application_id)
            raise ValidationError({"account_arn": error_code.get_message()})

        try:
            # Use get_or_create here in case there is another task running concurrently
            # that created the AwsCloudAccount at the same time.
            aws_cloud_account, created = AwsCloudAccount.objects.get_or_create(
                aws_account_id=aws_account_id,
                account_arn=arn_str,
                external_id=external_id,
            )
        except IntegrityError:
            # get_or_create can throw integrity error in the case that
            # aws_account_id xor arn already exists in an account.
            error_code = error_codes.CG1002
            error_code.notify(user.account_number, user.org_id, platform_application_id)
            raise ValidationError({"account_arn": error_code.get_message()})

        if not created:
            # If aws_account_id and arn already exist in an account because a
            # another task created it, notify the user.
            error_code = error_codes.CG1002
            error_code.notify(user.account_number, user.org_id, platform_application_id)
            raise ValidationError({"account_arn": error_code.get_message()})

        cloud_account = CloudAccount.objects.create(
            user=user,
            content_object=aws_cloud_account,
            platform_application_id=platform_application_id,
            platform_authentication_id=platform_authentication_id,
            platform_source_id=platform_source_id,
        )

        # This enable call *must* be inside the transaction because we need to
        # know to rollback the transaction if anything related to enabling fails.
        # Yes, this means holding the transaction open while we wait on calls
        # to AWS.
        if not cloud_account.enable(disable_upon_failure=False):
            # Enabling of cloud account failed, rolling back.
            transaction.set_rollback(True)
            raise ValidationError(
                {
                    "is_enabled": "Could not enable cloud account. "
                    "Please check your credentials."
                }
            )

    logger.info(_("Successfully created %(account)s"), {"account": cloud_account})
    return cloud_account


def update_aws_cloud_account(  # noqa: C901
    cloud_account,
    customer_arn,
    account_number,
    org_id,
    authentication_id,
    source_id,
    extra,
):
    """
    Update aws_cloud_account with the new arn.

    Args:
        cloud_account (api.models.CloudAccount)
        customer_arn (str): customer's ARN
        account_number (str): customer's account number
        authentication_id (str): Platform Sources' Authentication object id
        source_id (str): Platform Sources' Source object id
        extra (str): extras in auth object
    """
    logger.info(
        _(
            "Updating an AwsCloudAccount. "
            "cloud_account=%(cloud_account)s, "
            "customer_arn=%(customer_arn)s, "
            "account_number=%(account_number)s, "
            "authentication_id=%(authentication_id)s, "
            "source_id=%(source_id)s"
        ),
        {
            "cloud_account": cloud_account,
            "customer_arn": customer_arn,
            "account_number": account_number,
            "authentication_id": authentication_id,
            "source_id": source_id,
        },
    )
    application_id = cloud_account.platform_application_id
    external_id = None
    if extra is not None:
        external_id = extra.get("external_id")

    try:
        customer_aws_account_id = aws.AwsArn(customer_arn).account_id
    except InvalidArn:
        error = error_codes.CG1004
        error.log_internal_message(logger, {"application_id": application_id})
        error.notify(account_number, org_id, application_id)
        return

    # If the aws_account_id is different, then we disable the account,
    # delete all related instances, and then enable the account.
    # Otherwise just update the account_arn.
    if cloud_account.content_object.aws_account_id != customer_aws_account_id:
        logger.info(
            _(
                "Cloud Account with ID %(cloud_account_id)s and aws_account_id "
                "%(old_aws_account_id)s has received an update request for ARN "
                "%(new_arn)s and aws_account_id %(new_aws_account_id)s. "
                "Since the aws_account_id is different, Cloud Account ID "
                "%(cloud_account_id)s will be deleted. A new Cloud Account will be "
                "created with aws_account_id %(new_aws_account_id)s and arn "
                "%(new_arn)s."
            ),
            {
                "cloud_account_id": cloud_account.id,
                "old_aws_account_id": cloud_account.content_object.aws_account_id,
                "new_aws_account_id": customer_aws_account_id,
                "new_arn": customer_arn,
            },
        )

        # We don't need to notify sources here because we're just about to create the
        # new replacement CloudAccount which will also notify sources when enabled, and
        # we already have explicit calls to notify if we can't create the CloudAccount.
        cloud_account.disable(notify_sources=False)

        try:
            customer_aws_account_id = aws.AwsArn(customer_arn).account_id
        except InvalidArn:
            error = error_codes.CG1004
            error.log_internal_message(logger, {"application_id": application_id})
            error.notify(account_number, org_id, application_id)
            return

        # Verify that no AwsCloudAccount already exists with the same ARN.
        if AwsCloudAccount.objects.filter(account_arn=customer_arn).exists():
            error_code = error_codes.CG1001
            error_code.notify(account_number, org_id, application_id)
            return

        # Verify that no AwsCloudAccount already exists with the same AWS Account ID.
        if AwsCloudAccount.objects.filter(
            aws_account_id=customer_aws_account_id
        ).exists():
            error_code = error_codes.CG1002
            error_code.notify(account_number, org_id, application_id)
            return
        cloud_account.content_object.account_arn = customer_arn
        cloud_account.content_object.aws_account_id = customer_aws_account_id
        cloud_account.content_object.save()

        cloud_account.enable()

    else:
        try:
            cloud_account.content_object.account_arn = customer_arn
            cloud_account.content_object.save()
            verify_permissions(customer_arn, external_id)
            cloud_account.enable()
        except ValidationError as e:
            logger.info(
                _("ARN %s failed validation. The Cloud Account will still be updated."),
                customer_arn,
            )
            # Tell the cloud account why we're disabling it
            cloud_account.disable(message=str(e.detail))

        logger.info(
            _("Cloud Account with ID %s has been updated with arn %s. "),
            cloud_account.id,
            customer_arn,
        )
