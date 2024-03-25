"""Helper utility module to wrap up common AWS operations."""

import logging
from functools import wraps

from botocore.exceptions import ClientError
from django.utils.translation import gettext as _

from util.aws import AwsArn
from util.aws.sts import _get_primary_account_id, cloudigrade_policy
from util.exceptions import AwsThrottlingException, InvalidArn

logger = logging.getLogger(__name__)

COMMON_AWS_ACCESS_DENIED_ERROR_CODES = (
    "AccessDenied",
    "AccessDeniedException",
    "AuthFailure",
    "InsufficientDependencyServiceAccessPermissionException",
    "OptInRequired",
    "UnauthorizedOperation",
)


def verify_account_access(session):
    """
    Check role for proper access to AWS APIs.

    Args:
        session (boto3.Session): A temporary session tied to a customer account

    Returns:
        tuple[bool, list]: First element of the tuple indicates if role was
        verified, and the second element is a list of actions that failed.

    """
    success = True
    failed_actions = []
    for action in cloudigrade_policy["Statement"][0]["Action"]:
        if not _verify_policy_action(session, action):
            # Mark as failure, but keep looping so we can see each specific
            # failure in logs
            failed_actions.append(action)
            success = False
    return success, failed_actions


def _verify_policy_action(session, action):  # noqa: C901
    """
    Check to see if we have access to a specific action.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        action (str): The policy action to check

    Note:
        The "noqa: C901" comment on this function breaks my heart a little,
        but it's an exception to make our complexity checker be quiet when
        looking at this massive pile of "elif" blocks. Perhaps in an ideal
        world we would split up this function into a clever "policy action
        verifier factory" of sorts that might break the calls into separate
        functions, but for now, #JustTechnicalDebtThings.

    Returns:
        bool: Whether the action is allowed, or not.

    """
    sts = session.client("sts")
    try:
        if action == "sts:GetCallerIdentity":
            identity = sts.get_caller_identity()
            identity_arn = AwsArn(identity["Arn"])
            if str(identity_arn.account_id) == str(_get_primary_account_id()):
                logger.warning(
                    _(
                        "Customer policy has same AWS account ID as primary account. "
                        "This may indicate a misconfigured server or customer account."
                    )
                )
            return identity_arn.resource_type == "assumed-role"

        else:
            logger.warning(_('No test case exists for action "%s"'), action)
            return False
    except (ClientError, InvalidArn) as error:
        logger.info(_("Failed to verify policy. %(error)s"), {"error": error})
        return False


def rewrap_aws_errors(original_function):
    """
    Decorate function to except boto AWS ClientError and raise as RuntimeError.

    This is useful when we have boto calls inside of Celery tasks but Celery
    cannot serialize boto AWS ClientError using JSON. If we encounter other
    boto/AWS-specific exceptions that are not serializable, we should add
    support for them here.

    Args:
        original_function: The function to decorate.

    Returns:
        function: The decorated function.

    """

    @wraps(original_function)
    def wrapped(*args, **kwargs):
        try:
            result = original_function(*args, **kwargs)
        except ClientError as e:
            # Log the original exception to help us diagnose problems later.
            logger.info(e, exc_info=True)

            # Carefully dissect the object to avoid AttributeError and KeyError.
            response_error = getattr(e, "response", {}).get("Error", {})
            error_code = response_error.get("Code")

            if error_code in COMMON_AWS_ACCESS_DENIED_ERROR_CODES:
                # If we failed due to missing AWS permissions, return quietly for now.
                # This only typically happens if a user has changed their Role or Policy
                # after initial setup in a way that is incompatible with our needs.
                # We rely on sources-api to regularly hit our availability_check API
                # to periodically check the account and disable it if necessary.
                error_message = response_error.get("Message")
                message = _("Unexpected AWS {0}: {1}").format(error_code, error_message)
                logger.warning(message)
                return None
            elif error_code in ["ThrottlingException", "RequestLimitExceeded"]:
                logger.info(
                    "AWS Throttling error %s detected, raising AwsThrottlingException.",
                    e,
                )
                raise AwsThrottlingException
            else:
                message = _("Unexpected AWS error {0} ({1}): {2}").format(
                    type(e), error_code, e
                )
                raise RuntimeError(message)
        return result

    return wrapped
