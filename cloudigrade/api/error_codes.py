"""Collection of Cloudigrade error codes."""
from dataclasses import dataclass
from gettext import gettext as _

from util.insights import notify_sources_application_availability


GENERIC_ACCOUNT_SETUP_ERROR_MESSAGE = (
    "Could not set up cloud metering. Please contact support."
)

GENERIC_ACCOUNT_SETUP_ERROR_MESSAGE_WITH_ERROR_CODE = (
    GENERIC_ACCOUNT_SETUP_ERROR_MESSAGE + " Error code %(error_code)s."
)


@dataclass
class CloudigradeError:
    """Cloudigrade Error Class."""

    code: str
    internal_message: str
    message: str = _(GENERIC_ACCOUNT_SETUP_ERROR_MESSAGE_WITH_ERROR_CODE)

    def log_internal_message(self, logger, message_details):
        """Log an internal message for an error."""
        logger.warning(f"Error {self.code} encountered:")
        logger.warning(self.internal_message, message_details)

    def get_message(self):
        """Get the external message for an error."""
        return self.message % {"error_code": self.code}

    def notify(self, account_number, application_id, error_message=None):
        """Tell sources an application is not available because of error."""
        if not error_message:
            error_message = self.get_message()
        notify_sources_application_availability(
            account_number,
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
        "Failed to create Cloud Account for Sources Application id "
        "%(application_id)s: CloudAccount already exists with ARN %(arn)s."
    ),
)

# Duplicate AWS Account ID
CG1002 = CloudigradeError(
    "CG1002",
    _(
        "Failed to create Cloud Account for Sources Application id "
        "%(application_id)s: CloudAccount already exists with AWS Account ID "
        "for ARN %(arn)s."
    ),
)

# Duplicate Cloud Account Name
CG1003 = CloudigradeError(
    "CG1003",
    _(
        "Failed to create Cloud Account for Sources Application id "
        "%(application_id)s: CloudAccount already exists with name %(name)s."
    ),
)

# Invalid ARN
CG1004 = CloudigradeError(
    "CG1004",
    _(
        "Failed to create Cloud Account for Sources Application id "
        "%(application_id)s: Invalid ARN."
    ),
    _(GENERIC_ACCOUNT_SETUP_ERROR_MESSAGE + " Invalid ARN."),
)


# Use CG2*** for sources specific issues

# Sources Authentication Not Found
CG2000 = CloudigradeError(
    "CG2000",
    _(
        "Authentication ID %(authentication_id)s for account number "
        "%(account_number)s does not exist; aborting cloud account creation."
    ),
    _(
        GENERIC_ACCOUNT_SETUP_ERROR_MESSAGE_WITH_ERROR_CODE
        + " Attached Sources Authentication object does not exist."
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
        GENERIC_ACCOUNT_SETUP_ERROR_MESSAGE_WITH_ERROR_CODE
        + " Attached Authentication has unsupported authentication_type."
    ),
)


# Bad Resource Type
CG2002 = CloudigradeError(
    "CG2002",
    _(
        "Resource ID %(endpoint_id)s for account number %(account_number)s "
        "is not of type Endpoint; aborting cloud account creation."
    ),
    _(
        GENERIC_ACCOUNT_SETUP_ERROR_MESSAGE_WITH_ERROR_CODE
        + " Associated resource is not of type Endpoint."
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
        GENERIC_ACCOUNT_SETUP_ERROR_MESSAGE_WITH_ERROR_CODE
        + " No Endpoint Resource exist for Source."
    ),
)

# No Authentication Password provided
CG2004 = CloudigradeError(
    "CG2004",
    _("Missing expected password from authentication for id %(authentication_id)s"),
    _(
        GENERIC_ACCOUNT_SETUP_ERROR_MESSAGE_WITH_ERROR_CODE
        + " Attached Authentication missing password field."
    ),
)

# Use CG3*** for cloud account enablement issues
CG3000 = CloudigradeError(
    "CG3000",
    _("Failed to enable Cloud Account %(cloud_account_id)s: " "because %(exception)s"),
    _(
        "Could not enable cloud metering. "
        "Please contact support. Error code %(error_code)s."
    ),
)
