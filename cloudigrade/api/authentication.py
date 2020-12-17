"""Custom Cloudigrade Authentication Policies."""
import base64
import json
import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.utils.translation import gettext as _
from rest_framework import HTTP_HEADER_ENCODING
from rest_framework.authentication import BaseAuthentication, exceptions

logger = logging.getLogger(__name__)


def parse_requests_header(request):
    """
    Given a request, process it to get relevant header fields.

    Returns:
        (str, str, bool): the tuple of auth_header, account_number, is_org_admin
            fields. If the auth header is not present, this function returns
            (None, None, False)

    Raises:
        AuthenticationFailed: If any of the fields are malformed.
    """
    insights_request_id = request.META.get(settings.INSIGHTS_REQUEST_ID_HEADER, None)
    logger.info(
        _("Authenticating via insights, INSIGHTS_REQUEST_ID: %s"),
        insights_request_id,
    )

    auth_header = request.META.get(settings.INSIGHTS_IDENTITY_HEADER, None)

    # Can't authenticate if there isn't a header
    if not auth_header:
        return None, None, False
    try:
        auth = json.loads(base64.b64decode(auth_header).decode(HTTP_HEADER_ENCODING))

    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.info(_("Authentication Failed: 3scale header parsing error %s"), e)
        raise exceptions.AuthenticationFailed(
            _("Authentication Failed: invalid 3scale header- {error}").format(error=e)
        )

    if settings.VERBOSE_INSIGHTS_IDENTITY_HEADER_LOGGING:
        # Important note: this setting defaults to False and generally should remain
        # as False except for very special and *temporary* circumstances when we need
        # to investigate unusual request handling.
        logger.info(_("Decoded 3scale header: %s"), str(auth))

    # If account_number is not in header, authentication fails
    try:
        account_number = auth["identity"]["account_number"]
    except KeyError:
        logger.info(
            _(
                "Authentication Failed: "
                "account_number not contained "
                "in 3scale header %s."
            ),
            auth_header,
        )
        raise exceptions.AuthenticationFailed(
            _(
                "Authentication Failed: invalid 3scale header- "
                "missing user account_number field"
            )
        )

    is_org_admin = auth["identity"].get("user", {}).get("is_org_admin")
    logger.info(
        _(
            "3scale header has identity "
            "account_number '%(account_number)s' "
            "is_org_admin '%(is_org_admin)s'"
        ),
        {"account_number": account_number, "is_org_admin": is_org_admin},
    )
    return auth_header, account_number, is_org_admin


class ThreeScaleAuthentication(BaseAuthentication):
    """
    Authentication class that uses 3scale headers to find Django Users.

    This authentication requires the 3scale header to exist with an identity having
    org_admin enabled. If we cannot find a User matching the 3scale identity, then
    authentication fails and returns None.
    """

    require_org_admin = True
    require_user = True

    def assert_org_admin(self, account_number, is_org_admin):
        """
        Assert org_admin is set if required.

        This functionality arguably belongs in a Permission class, not an Authentication
        class, but it's simply convenient to include here because this assertion
        requires parsing the 3scale header, and we've already done that here to get the
        3scale identity account number.
        """
        if self.require_org_admin and not is_org_admin:
            logger.info(
                _(
                    "Authentication Failed: Identity user %(account_number)s"
                    "is not org admin in 3scale header."
                ),
                {"account_number": account_number},
            )
            raise exceptions.PermissionDenied(_("User must be an org admin."))

    def get_user(self, account_number):
        """Get the Django User for the account number."""
        if User.objects.filter(username=account_number).exists():
            return User.objects.get(username=account_number)
        elif self.require_user:
            message = _(
                "Authentication Failed: user with account number {username} "
                "does not exist."
            ).format(username=account_number)
            logger.info(message)
            raise exceptions.AuthenticationFailed(message)
        return None

    def authenticate(self, request):
        """Authenticate the request using the 3scale identity."""
        auth_header, account_number, is_org_admin = parse_requests_header(request)

        # Can't authenticate if there isn't a header
        if not auth_header or not account_number:
            return None

        self.assert_org_admin(account_number, is_org_admin)
        if user := self.get_user(account_number):
            return user, True
        return None


class ThreeScaleAuthenticationInternal(ThreeScaleAuthentication):
    """
    Authentication class that only optionally uses 3scale headers.

    This authentication checks for the 3scale header but does not require the identity
    to exist or to have org_admin enabled. If we cannot find a User matching the 3scale
    identity, then authentication fails and returns None. We expect the downstream view
    to determine if access should be allowed if no authentication exists.

    Why is this "optional" variation necessary? Internal Red Hat Cloud services do not
    consistently set the org_admin value, and we want to grant generally broad access to
    our internal APIs.
    """

    require_org_admin = False
    require_user = False
