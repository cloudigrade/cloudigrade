"""Utility functions for AWS models and use cases."""
import logging

from botocore.exceptions import ClientError
from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import error_codes
from api.clouds.aws.models import (
    AwsCloudAccount,
    AwsMachineImage,
    AwsMachineImageCopy,
)
from api.models import (
    CloudAccount,
    Instance,
    MachineImage,
)
from util import aws
from util.exceptions import InvalidArn

logger = logging.getLogger(__name__)


def create_aws_machine_image_copy(copy_ami_id, reference_ami_id):
    """
    Create an AwsMachineImageCopy given the copy and reference AMI IDs.

    Args:
        copy_ami_id (str): the AMI IS of the copied image
        reference_ami_id (str): the AMI ID of the original reference image
    """
    with transaction.atomic():
        reference = AwsMachineImage.objects.get(ec2_ami_id=reference_ami_id)
        awsmachineimagecopy = AwsMachineImageCopy.objects.create(
            ec2_ami_id=copy_ami_id,
            owner_aws_account_id=reference.owner_aws_account_id,
            reference_awsmachineimage=reference,
        )
        MachineImage.objects.create(content_object=awsmachineimagecopy)

        # This should not be necessary, but we really need this to exist.
        # If it doesn't, this will kill the transaction with an exception.
        awsmachineimagecopy.machine_image.get()


def verify_permissions(customer_role_arn):  # noqa: C901
    """
    Verify AWS permissions.

    This function may raise ValidationError if certain verification steps fail.

    Args:
        customer_role_arn (str): ARN to access the customer's AWS account

    Note:
        This function not only verifies; it also has the side effect of configuring
        the AWS CloudTrail. This should be refactored into a more explicit operation,
        but at the time of this writing, there is no "dry run" check for CloudTrail
        operations. Callers should be aware of the risk that we may configure CloudTrail
        but somewhere else rollback our transaction, leaving that Trail orphaned.

        This function also has the side-effect of notifying sources and updating the
        application status to unavailable if we cannot complete processing normally.

    Returns:
        boolean indicating if the verification and CloudTrail setup succeeded.

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

    if cloud_account.is_synthetic:
        # Synthetic accounts should never have real AWS accounts, CloudTrail, etc.
        # but we should return early and treat them as if all systems are go.
        return True

    # Get the username immediately from the related user in case the user is deleted
    # while we are verifying access; we'll need it later
    # in order to notify sources of our error.
    account_number = cloud_account.user.account_number
    org_id = cloud_account.user.org_id

    try:
        session = aws.get_session(arn_str)
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
        ),
        {
            "user": user.account_number,
            "customer_role_arn": customer_role_arn,
            "platform_authentication_id": platform_authentication_id,
            "platform_application_id": platform_application_id,
            "platform_source_id": platform_source_id,
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
                aws_account_id=aws_account_id, account_arn=arn_str
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


def update_aws_cloud_account(
    cloud_account,
    customer_arn,
    account_number,
    org_id,
    authentication_id,
    source_id,
):
    """
    Update aws_cloud_account with the new arn.

    Args:
        cloud_account (api.models.CloudAccount)
        customer_arn (str): customer's ARN
        account_number (str): customer's account number
        authentication_id (str): Platform Sources' Authentication object id
        source_id (str): Platform Sources' Source object id
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
        cloud_account.disable(power_off_instances=False, notify_sources=False)

        # Remove instances associated with the cloud account
        # TODO instead of deleting instances here, delete the original CloudAccount.
        # We can't delete it here due to 7b02f90fc643533246e51f20078e8ae2366df32b, but
        # we could delete it after we've created the new CloudAccount a few lines later.
        Instance.objects.filter(cloud_account=cloud_account).delete()

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
            verify_permissions(customer_arn)
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


def delete_cloudtrail(aws_cloud_account):
    """
    Delete an AwsCloudAccount's CloudTrail.

    Note:
        If the incoming AwsCloudAccount instance is being deleted, this call to
        delete_cloudtrail may occur after the DB record has been deleted, and we are
        only working with a shallow reference copy of the AwsCloudAccount. This means we
        cannot reliably load related objects (e.g. aws_cloud_account.cloud_account).

    Args:
        aws_cloud_account (api.clouds.aws.models.AwsCloudAccount): the AwsCloudAccount
            for which we should delete the CloudTrail

    Returns:
        bool True if CloudTrail was successfully deleted, else False.

    """
    cloudtrail_name = aws.get_cloudtrail_name(aws_cloud_account.cloud_account_id)

    try:
        session = aws.get_session(str(aws_cloud_account.account_arn))
        cloudtrail_session = session.client("cloudtrail")
        logger.info(
            "attempting to delete cloudtrail '%(name)s' via ARN '%(arn)s'",
            {"name": cloudtrail_name, "arn": aws_cloud_account.account_arn},
        )
        aws.delete_cloudtrail(cloudtrail_session, cloudtrail_name)
        return True

    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code")
        if error_code == "TrailNotFoundException":
            # If a cloudtrail does not exist, then we have nothing to do here!
            return True
        elif error_code in aws.COMMON_AWS_ACCESS_DENIED_ERROR_CODES:
            # We may get AccessDenied if the user deletes the AWS account or role.
            # We may get AccessDeniedException if the role or policy is broken.
            # These could result in an orphaned cloudtrail writing to our s3 bucket.
            logger.warning(
                _(
                    "AwsCloudAccount ID %(aws_cloud_account_id)s for AWS account ID "
                    "%(aws_account_id)s encountered %(error_code)s and cannot "
                    "delete cloudtrail %(cloudtrail_name)s."
                ),
                {
                    "aws_cloud_account_id": aws_cloud_account.id,
                    "aws_account_id": aws_cloud_account.cloud_account_id,
                    "error_code": error_code,
                    "cloudtrail_name": cloudtrail_name,
                },
            )
            logger.info(error)
        else:
            logger.exception(error)
            logger.error(
                _(
                    "Unexpected error %(error_code)s occurred disabling CloudTrail "
                    "%(cloudtrail_name)s for AwsCloudAccount ID "
                    "%(aws_cloud_account_id)s. "
                ),
                {
                    "error_code": error_code,
                    "cloudtrail_name": cloudtrail_name,
                    "aws_cloud_account_id": aws_cloud_account.id,
                },
            )
    return False
