"""Authentication classes for cloudigrade internal APIs."""
from api.authentication import IdentityHeaderAuthentication


class IdentityHeaderAuthenticationInternal(IdentityHeaderAuthentication):
    """
    Authentication class that only optionally uses the identity header.

    This authentication checks for the identity header but does not require the identity
    to exist or to have org_admin enabled. If we cannot find a User matching the header
    identity, then authentication fails and returns None. We expect the downstream view
    to determine if access should be allowed if no authentication exists.

    This "optional" variant exists because internal Red Hat Cloud services do not
    consistently set the org_admin value, and we want to grant generally broad access to
    our internal APIs.
    """

    require_org_admin = False
    require_account_number = False
    require_user = False
    create_user = False


class IdentityHeaderAuthenticationInternalCreateUser(IdentityHeaderAuthentication):
    """
    Authentication class that uses identity header to creates Users.

    This authentication checks for the identity header but does not require the identity
    to have org_admin enabled. If we cannot find a User matching the header's identity,
    then we create a new User from the identity header's account number.
    """

    require_org_admin = False
    require_account_number = True
    require_user = False
    create_user = True


class IdentityHeaderAuthenticationInternalConcurrent(IdentityHeaderAuthentication):
    """
    Authentication class that uses identity header to query/trigger concurrent reports.

    This authentication checks for the identity header and requires the identity
    to have org_admin enabled.
    """

    require_org_admin = True
    require_account_number = True
    require_user = True
    create_user = False
    support_account_number_header = True
    support_org_admin_header = True
