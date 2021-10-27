"""Authentication classes for cloudigrade APIs."""
import base64
import binascii
import json
import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import HTTP_HEADER_ENCODING
from rest_framework.authentication import BaseAuthentication, exceptions

logger = logging.getLogger(__name__)


def psk_service_name(psk):
    """Given a PSK, this function returns the related service name."""
    for svc_name, svc_psk in settings.CLOUDIGRADE_PSKS.items():
        if psk == svc_psk:
            return svc_name

    return None


def parse_insights_request_id(request):
    """Parse and log the Insights Request ID."""
    insights_request_id = request.META.get(settings.INSIGHTS_REQUEST_ID_HEADER, None)
    logger.info(
        _("Authenticating via insights, INSIGHTS_REQUEST_ID: %s"),
        insights_request_id,
    )


def parse_psk_header(request):
    """
    Get relevant information from the given request's PSK and account number headers.

    Returns:
        (str, str): the tuple of psk and account_number fields.
            If the psk header is not present and the account_number
            header is specified, this function returns (None, None).
            Otherwise it will return (str, str|None) with the valid
            PSK and the account_number if specified.

    Raises:
        AuthenticationFailed: If an invalid PSK is specified.
    """
    service_psk = request.META.get(settings.CLOUDIGRADE_PSK_HEADER, None)

    if service_psk is None:
        return None, None

    service_name = psk_service_name(service_psk)
    if not service_name:
        logger.info(
            _("Authentication Failed: Invalid PSK '%s' specified in header"),
            service_psk,
        )
        raise exceptions.AuthenticationFailed(
            _("Authentication Failed: Invalid PSK specified in header")
        )

    account_number = request.META.get(settings.CLOUDIGRADE_ACCOUNT_NUMBER_HEADER, None)

    if account_number is None:
        logger.info(
            _("PSK header for service '%(service_name)s' with no account_number"),
            {
                "service_name": service_name,
            },
        )
        return service_psk, None

    logger.info(
        _(
            "PSK header for service '%(service_name)s'"
            " with account_number '%(account_number)s'"
        ),
        {
            "service_name": service_name,
            "account_number": account_number,
        },
    )
    return service_psk, account_number


def parse_requests_header(request, allow_internal_fake_identity_header=False):
    """
    Get relevant information from the given request's identity header.

    Returns:
        (str, str, bool): the tuple of psk and account_number fields. Both psk
            and account_number headers must be specified in the request.
            If the psk header is not present or invalid and the account_number
            header is missing, this function returns (None, None)

    Raises:
        AuthenticationFailed: If any of the fields are invalid or missing.
    """
    auth_header = request.META.get(settings.INSIGHTS_IDENTITY_HEADER, None)
    if allow_internal_fake_identity_header:
        auth_header = request.META.get(
            settings.INSIGHTS_INTERNAL_FAKE_IDENTITY_HEADER, auth_header
        )

    # Can't authenticate if there isn't a header
    if not auth_header:
        return None, None, False
    try:
        auth = json.loads(base64.b64decode(auth_header).decode(HTTP_HEADER_ENCODING))

    except (TypeError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as e:
        logger.info(_("Authentication Failed: identity header parsing error %s"), e)
        logger.info(_("Raw header was: %s"), auth_header)
        raise exceptions.AuthenticationFailed(
            _("Authentication Failed: invalid identity header- {error}").format(error=e)
        )

    if settings.VERBOSE_INSIGHTS_IDENTITY_HEADER_LOGGING:
        # Important note: this setting defaults to False and generally should remain
        # as False except for very special and *temporary* circumstances when we need
        # to investigate unusual request handling.
        logger.info(_("Decoded identity header: %s"), str(auth))

    identity = auth.get("identity", {})

    # If account_number is not in header, authentication fails
    account_number = identity.get("account_number")
    if not account_number:
        logger.info(
            _("account_number not contained in identity header %s."),
            auth_header,
        )

    user = identity.get("user", {})
    is_org_admin = user.get("is_org_admin")
    username = user.get("username")
    email = user.get("email")
    logger.info(
        _(
            "identity header has account_number '%(account_number)s', "
            "is_org_admin '%(is_org_admin)s', username '%(username)s', "
            "email '%(email)s'"
        ),
        {
            "account_number": account_number,
            "is_org_admin": is_org_admin,
            "username": username,
            "email": email,
        },
    )
    return auth_header, account_number, is_org_admin


class IdentityHeaderAuthentication(BaseAuthentication):
    """
    Authentication class that uses identity headers to find Django Users.

    This authentication requires the identity header to exist with an identity having
    org_admin enabled. If we cannot find a User matching the identity, then
    authentication fails and returns None.
    """

    require_org_admin = True
    require_account_number = True
    require_user = True
    create_user = False
    allow_internal_fake_identity_header = False

    def assert_account_number(self, account_number):
        """Assert account_number is set if required."""
        if not account_number and self.require_account_number:
            raise exceptions.AuthenticationFailed(
                _(
                    "Authentication Failed: identity account number is required "
                    "but was not present in request."
                )
            )

    def assert_org_admin(self, account_number, is_org_admin):
        """
        Assert org_admin is set if required.

        This functionality arguably belongs in a Permission class, not an Authentication
        class, but it's simply convenient to include here because this assertion
        requires parsing the identity header, and we've already done that here to get
        the identity account number.
        """
        if self.require_org_admin and not is_org_admin:
            logger.info(
                _(
                    "Authentication Failed: identity account number %(account_number)s"
                    "is not org admin in identity header."
                ),
                {"account_number": account_number},
            )
            raise exceptions.PermissionDenied(_("User must be an org admin."))

    def get_user(self, account_number):
        """Get the Django User for the account number."""
        if not account_number:
            return None

        user = None
        if self.create_user:
            # Note: Declaring this transaction might not be necessary since we have
            # ATOMIC_REQUESTS default to True, but since it's *possible* to disable that
            # setting, this bit of paranoia ensures the User and UserTaskLock are always
            # created together in a shared transaction.
            with transaction.atomic():
                user, created = User.objects.get_or_create(username=account_number)
                if created:
                    user.set_unusable_password()
                    logger.info(
                        _("Username %s was not found and has been created."),
                        account_number,
                    )
                    from api.models import UserTaskLock  # local import to avoid loop

                    UserTaskLock.objects.get_or_create(user=user)
        elif User.objects.filter(username=account_number).exists():
            user = User.objects.get(username=account_number)
            logger.info(
                _("Authentication found user with username %(account_number)s"),
                {"account_number": account_number},
            )
        elif self.require_user:
            message = _(
                "Authentication Failed: user with account number {username} "
                "does not exist."
            ).format(username=account_number)
            logger.info(message)
            raise exceptions.AuthenticationFailed()
        else:
            logger.info(
                _("Username %s was not found but is not required."),
                account_number,
            )
        logger.debug(
            _("Authenticated user for username %(account_number)s is %(user)s"),
            {"account_number": account_number, "user": user},
        )
        return user

    def authenticate(self, request):
        """Authenticate the request using the PSK or the identity header."""
        parse_insights_request_id(request)
        psk, account_number = parse_psk_header(request)
        if psk:
            self.assert_account_number(account_number)
        else:
            auth_header, account_number, is_org_admin = parse_requests_header(
                request, self.allow_internal_fake_identity_header
            )

            # Can't authenticate if there isn't a header
            if not auth_header:
                if not self.require_account_number and not self.require_org_admin:
                    return None
                else:
                    raise exceptions.AuthenticationFailed

            self.assert_account_number(account_number)
            self.assert_org_admin(account_number, is_org_admin)
        if user := self.get_user(account_number):
            return user, True
        return None


class IdentityHeaderAuthenticationUserNotRequired(IdentityHeaderAuthentication):
    """
    Authentication class that does not require a User to exist for the account number.

    This authentication checks for the identity header and requires the identity to
    exist with an account number and with org_admin enabled. However, this does not
    require that a User matching the identity's account number exists.

    This variant exists because at least one public API (sysconfig) needs to have access
    restricted to an authenticated Red Hat identity before a corresponding User may have
    been created within our system.
    """

    require_org_admin = True
    require_account_number = True
    require_user = False
    create_user = False
