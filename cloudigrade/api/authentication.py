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
    3scale authentication. User must be an org admin.

    Check for the existence of a INSIGHTS_IDENTITY_HEADER. The user identity is
    inferred based off the email in the header.
    """

    def authenticate(self, request):
        """
        Return a `User` if a valid INSIGHTS_IDENTITY_HEADER is present.

        Returns:
            None: If authentication is not provided
            User, True: If authentication succeeds.

        Raises:
            AuthenticationFailed: If the user attempts and fail to authenticate
            PermissionDenied: If the user is not an org admin

        """
        auth_header, account_number, is_org_admin = parse_requests_header(request)

        # Can't authenticate if there isn't a header
        if not auth_header:
            return None

        if not is_org_admin:
            logger.info(
                _(
                    "Authentication Failed: identity user is not org admin "
                    "in 3scale header %s."
                ),
                auth_header,
            )
            raise exceptions.PermissionDenied(_("User must be an org admin."))

        user, created = User.objects.get_or_create(username=account_number)
        if created:
            user.set_unusable_password()
            logger.info(
                _("User %s was not found and has been created."),
                account_number,
            )
        return user, True


class ThreeScaleAuthenticationNoOrgAdmin(BaseAuthentication):
    """
    3scale authentication. User does not have to be an org admin.

    Why is this necessary?
    See https://gitlab.com/cloudigrade/cloudigrade/-/issues/689

    Check for the existence of a INSIGHTS_IDENTITY_HEADER. The user identity is
    inferred based off the email in the header.
    """

    def authenticate(self, request):
        """
        Return a `User` if a valid INSIGHTS_IDENTITY_HEADER is present.

        Returns:
            None: If authentication is not provided, or if a cloudigrade user
                with the given account_number does not exist.
            User, True: If authentication succeeds.

        Raises:
            AuthenticationFailed: If the user attempts and fail to authenticate

        """
        auth_header, account_number, is_org_admin = parse_requests_header(request)

        # Can't authenticate if there isn't a header
        if not auth_header:
            return None

        if not User.objects.filter(username=account_number).exists():
            logger.info(
                _("Authentication Failed: user %s does not exist."),
                account_number,
            )
            raise exceptions.AuthenticationFailed(
                _("Authentication Failed: user {username} does not exist.").format(
                    username=account_number
                )
            )
        user = User.objects.get(username=account_number)
        return user, True
