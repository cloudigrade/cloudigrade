"""Authentication classes for cloudigrade internal APIs."""

from api.authentication import IdentityHeaderAuthentication


class IdentityHeaderAuthenticationInternal(IdentityHeaderAuthentication):
    """
    Authentication class that only optionally uses the identity header.

    This authentication checks for the identity header but does not require the identity
    to exist. If we cannot find a User matching the header identity, then authentication
    fails and gracefully returns None. We expect the downstream view to determine if
    access should be allowed if no authentication exists.

    This "optional" variant exists because internal Red Hat console services do not
    consistently set the identity header, and we want to grant generally broad access
    to some of our internal APIs.
    """

    require_account_number_or_org_id = False
    require_user = False
    create_user = False


class IdentityHeaderAuthenticationInternalCreateUser(IdentityHeaderAuthentication):
    """
    Authentication class that uses identity header to create Users.

    This authentication checks for a User matching the attributes in the identity
    header, but if a matching User is not found, then we create a new User.
    """

    require_account_number_or_org_id = True
    require_user = False
    create_user = True


class IdentityHeaderAuthenticationInternalAllowFakeIdentityHeader(
    IdentityHeaderAuthentication
):
    """
    Authentication class that uses an alternate HTTP header for the identity definition.

    This authentication checks the custom INSIGHTS_INTERNAL_FAKE_IDENTITY_HEADER header
    before checking the normal INSIGHTS_IDENTITY_HEADER header. This enables us to make
    internal requests simulating other users because the 3scale gateway populates the
    normal INSIGHTS_IDENTITY_HEADER header which we cannot override.
    """

    require_account_number_or_org_id = True
    require_user = True
    create_user = False
    allow_internal_fake_identity_header = True
