"""Collection of Cloudigrade error codes."""
from dataclasses import dataclass
from gettext import gettext as _

from django.conf import settings

GENERIC_ERROR_MESSAGE = "Could not enable cloud metering."
GENERIC_ERROR_MESSAGE_WITH_CODE = f"{GENERIC_ERROR_MESSAGE} Error code %(error_code)s."


@dataclass
class CloudigradeError:
    """Cloudigrade Error Class."""

    code: str
    internal_message: str
    message: str = _(GENERIC_ERROR_MESSAGE_WITH_CODE)

    def log_internal_message(self, logger, message_details):
        """Log an internal message for an error."""
        logger.warning(f"Error {self.code} encountered:")
        logger.warning(self.internal_message, message_details)

    def get_message(self):
        """Get the external message for an error."""
        return self.message % {"error_code": self.code}

    def notify(self, account_number, org_id, application_id, error_message=None):
        """Tell sources an application is not available because of error."""
        from api.tasks.sources import notify_application_availability_task

        if not error_message:
            error_message = self.get_message()
        notify_application_availability_task.delay(
            account_number,
            org_id,
            application_id,
            availability_status="unavailable",
            availability_status_error=error_message,
        )


# Use CG1*** for internal cloudigrade account creation issues

# Username Not Found
CG1000 = CloudigradeError(
    "CG1000",
    _(
        "Failed to create Cloud Account for Sources Application id "
        "%(application_id)s: userID %(username)s not found."
    ),
)

# Duplicate ARN
CG1001 = CloudigradeError(
    "CG1001",
    _(
        "Failed to create cloud account for Sources Application ID %(application_id)s "
        "because a cloud account already exists with ARN %(arn)s."
    ),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} AWS ARN must be unique, but "
        "another cloud account with the same AWS ARN already exists."
    ),
)

# Duplicate AWS Account ID
CG1002 = CloudigradeError(
    "CG1002",
    _(
        "Failed to create cloud account for Sources Application ID %(application_id)s "
        "because a cloud account already exists with AWS Account ID %(account_id)s."
    ),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} AWS account ID must be unique, but "
        "another cloud account with the same AWS account ID already exists."
    ),
)

# Invalid ARN
CG1004 = CloudigradeError(
    "CG1004",
    _(
        "Failed to create Cloud Account for Sources Application id "
        "%(application_id)s: Invalid ARN."
    ),
    _(f"{GENERIC_ERROR_MESSAGE_WITH_CODE} Invalid ARN."),
)

# Duplicate Azure subscription ID
CG1005 = CloudigradeError(
    "CG1005",
    _(
        "Failed to create cloud account for Sources Application ID %(application_id)s "
        "because a cloud account already exists with Azure subscription ID "
        "%(subscription_id)s."
    ),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} Azure subscription ID must be unique, but "
        "another cloud account with the same Azure subscription ID already exists."
    ),
)

# Invalid Azure subscription ID
CG1006 = CloudigradeError(
    "CG1006",
    _(
        "Failed to create Cloud Account for Sources Application id "
        "%(application_id)s: Invalid Azure subscription ID."
    ),
    _(f"{GENERIC_ERROR_MESSAGE_WITH_CODE} Invalid Azure subscription ID."),
)


# Use CG2*** for sources specific issues
SOURCES_API_ERROR_MESSAGE = "This is likely the result of an error in sources-api."

# Sources Authentication Not Found
CG2000 = CloudigradeError(
    "CG2000",
    _(
        "Authentication ID %(authentication_id)s for account number "
        "%(account_number)s does not exist; aborting cloud account creation."
    ),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} Required authentication was not found. "
        f"{SOURCES_API_ERROR_MESSAGE}"
    ),
)

#   Bad Authentication Type
CG2001 = CloudigradeError(
    "CG2001",
    _(
        "Aborting creation. Authentication ID %(authentication_id)s is of "
        "unsupported type %(authtype)s.",
    ),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} The authentication has unsupported type; "
        f"type must be {' or '.join(settings.SOURCES_CLOUDMETER_AUTHTYPES)}. "
        f"{SOURCES_API_ERROR_MESSAGE}"
    ),
)


# Bad Resource Type
CG2002 = CloudigradeError(
    "CG2002",
    _(
        "Resource ID %(resource_id)s for account number %(account_number)s "
        "is not of type Application; aborting cloud account creation."
    ),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} The authentication's resource has "
        f"unsupported type; type must be {settings.SOURCES_RESOURCE_TYPE}. "
        f"{SOURCES_API_ERROR_MESSAGE}"
    ),
)


# Endpoint Does not Exist
CG2003 = CloudigradeError(
    "CG2003",
    _(
        "Endpoint ID %(endpoint_id)s for account number "
        "%(account_number)s does not exist; aborting cloud account creation."
    ),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} Required endpoint resource was not found. "
        f"{SOURCES_API_ERROR_MESSAGE}"
    ),
)

# No Authentication Username/Password provided
CG2004 = CloudigradeError(
    "CG2004",
    _(
        "Missing expected username/password from authentication for "
        "id %(authentication_id)s"
    ),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} Authentication did not include required "
        "Authentication Token in either username or password field."
    ),
)

# Use CG3*** for cloud account enablement issues
CG3000 = CloudigradeError(
    "CG3000",
    _("Failed to enable Cloud Account %(cloud_account_id)s: because %(exception)s"),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} Encountered unknown issue with provided "
        "credentials. Please verify provided credentials and try again."
    ),
)

# Too many cloudtrails
CG3001 = CloudigradeError(
    "CG3001",
    _("Failed to enable Cloud Account %(cloud_account_id)s: because %(exception)s"),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} You've reached the AWS CloudTrail limit "
        "for your account. Please ensure you have not reached the CloudTrail limit for "
        "your account, and try again."
    ),
)

# Misconfigured role
CG3002 = CloudigradeError(
    "CG3002",
    _("Failed to enable Cloud Account %(cloud_account_id)s: because %(exception)s"),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} An AccessDenied error was received when "
        "using the ARN, suggesting that the AWS role is misconfigured. Please verify "
        "the AWS role and try again."
    ),
)

# Misconfigured Policy
CG3003 = CloudigradeError(
    "CG3003",
    _("Failed to enable Cloud Account %(cloud_account_id)s: because %(exception)s"),
    _(
        f"{GENERIC_ERROR_MESSAGE_WITH_CODE} Failed to verify at least one AWS policy "
        "action, suggesting that the policy attached to the role is misconfigured. "
        "Please verify the AWS policy and try again."
    ),
)
