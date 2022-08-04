"""Authentication classes for cloudigrade APIs."""
import base64
import binascii
import json
import logging

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import HTTP_HEADER_ENCODING
from rest_framework.authentication import BaseAuthentication, exceptions

from api.models import User

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
        (str, str, str): the tuple of psk, account_number and/or org_id fields.
            If the psk header is not present and the account_number or org_id
            header is specified, this function returns (None, None, None).
            Otherwise, it will return (str, str|None, str|None) with the valid
            PSK and the account_number and/or org_id if specified.

    Raises:
        AuthenticationFailed: If an invalid PSK is specified.
    """
    service_psk = request.META.get(settings.CLOUDIGRADE_PSK_HEADER, None)

    if service_psk is None:
        return None, None, None

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
    org_id = request.META.get(settings.CLOUDIGRADE_ORG_ID_HEADER, None)

    if not account_number and not org_id:
        logger.info(
            _(
                "PSK header for service '%(service_name)s'"
                " with no account_number or org_id"
            ),
            {
                "service_name": service_name,
            },
        )
        return service_psk, None, None

    logger.info(
        _(
            "PSK header for service '%(service_name)s'"
            " with account_number '%(account_number)s' and org_id '%(org_id)s'"
        ),
        {
            "service_name": service_name,
            "account_number": account_number,
            "org_id": org_id,
        },
    )
    return service_psk, account_number, org_id


def get_user_by_account(account_number=None, org_id=None):
    """
    Given an account_number or org_id, return the user object.

    Returns:
        User object matching the account_number or org_id
        specified, None otherwise.
    """
    if account_number and org_id:
        return User.objects.get(account_number=account_number, org_id=org_id)

    if account_number:
        return User.objects.get(account_number=account_number)

    if org_id:
        return User.objects.get(org_id=org_id)

    raise User.DoesNotExist("User matching account_number or org_id does not exist.")


def get_or_create_user(account_number, org_id):
    """
    Get or create a user with the specified account_number and org_id.

    Returns:
        Auth user object found or created
    """
    # Note: Declaring this transaction might not be necessary since we have
    # ATOMIC_REQUESTS default to True, but since it's *possible* to disable that
    # setting, this bit of paranoia ensures the User and UserTaskLock are always
    # created together in a shared transaction.
    user = None
    with transaction.atomic():
        if account_number and org_id:
            user, created = User.objects.get_or_create(
                account_number=account_number, defaults={"org_id": org_id}
            )
        elif account_number:
            user, created = User.objects.get_or_create(account_number=account_number)
        elif org_id:
            user, created = User.objects.get_or_create(org_id=org_id)
        if created:
            user.set_unusable_password()
            user.save()
            logger.info(
                _(
                    "account_number '%s' and org_id '%s'"
                    "was not found and has been created."
                ),
                account_number,
                org_id,
            )
            from api.models import UserTaskLock  # local import to avoid loop

            UserTaskLock.objects.get_or_create(user=user)
        elif org_id and not user.org_id:
            user.org_id = org_id
            user.save()
    return user


def parse_requests_header(request, allow_internal_fake_identity_header=False):
    """
    Get relevant information from the given request's identity header.

    Returns:
        (str, str, str): the tuple of psk, account_number and org_id fields.
            Both psk and either account_number or org_id headers must be specified
            in the request. If the psk header is not present or invalid and
            the account_number or org_id header is missing, this function
            returns (None, None, None)

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
        return None, None, None
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
    org_id = identity.get("org_id")
    # If account_number or org_id is not in header, authentication fails
    if not account_number and not org_id:
        logger.info(
            _("account_number or org_id not contained in identity header %s."),
            auth_header,
        )

    user = identity.get("user", {})
    username = user.get("username")
    email = user.get("email")
    logger.info(
        _(
            "identity header has "
            "account_number '%(account_number)s', "
            "org_id '%(org_id)s', "
            "username '%(username)s', "
            "email '%(email)s'"
        ),
        {
            "account_number": account_number,
            "org_id": org_id,
            "username": username,
            "email": email,
        },
    )
    return auth_header, account_number, org_id


class IdentityHeaderAuthentication(BaseAuthentication):
    """
    Authentication class that uses identity headers to find Django Users.

    This authentication requires the identity header to exist with an identity having
    an account_number. If we cannot find a User matching the identity, then
    authentication fails and returns None.
    """

    require_account_number = True
    require_user = True
    create_user = False
    allow_internal_fake_identity_header = False

    def assert_account_number(self, account_number, org_id):
        """Assert account_number or org_id is set if required."""
        if not account_number and not org_id and self.require_account_number:
            raise exceptions.AuthenticationFailed(
                _(
                    "Authentication Failed: identity account number is required "
                    "but account_number or org_id was not present in request."
                )
            )

    def get_user(self, account_number, org_id):
        """Get the Django User for the account_number or org_id specified."""
        if not account_number and not org_id:
            return None

        user = None
        if self.create_user:
            user = get_or_create_user(account_number, org_id)
        elif (
            account_number
            and User.objects.filter(account_number=account_number).exists()
        ):
            user = User.objects.get(account_number=account_number)
            logger.info(
                _("Authentication found user with account_number %(account_number)s"),
                {"account_number": account_number},
            )
        elif org_id and User.objects.filter(org_id=org_id).exists():
            user = User.objects.get(org_id=org_id)
            logger.info(
                _("Authentication found user with org_id %(org_id)s"),
                {"org_id": org_id},
            )
        elif self.require_user:
            message = _(
                "Authentication Failed: user with account_number '{account_number}', "
                " org_id '{org_id}' does not exist."
            ).format(account_number=account_number, org_id=org_id)
            logger.info(message)
            raise exceptions.AuthenticationFailed()
        else:
            logger.info(
                _(
                    "account_number '%s' or org_id '%s'"
                    " was not found but is not required."
                ),
                account_number,
                org_id,
            )
        logger.debug(
            _(
                "Authenticated user for account_number '%(account_number)s', "
                " org_id '%(org_id)s' is %(user)s"
            ),
            {"account_number": account_number, "org_id": org_id, "user": user},
        )
        return user

    def authenticate(self, request):
        """Authenticate the request using the PSK or the identity header."""
        parse_insights_request_id(request)
        psk, account_number, org_id = parse_psk_header(request)

        if psk:
            self.assert_account_number(account_number, org_id)
        else:
            auth_header, account_number, org_id = parse_requests_header(
                request, self.allow_internal_fake_identity_header
            )

            # Can't authenticate if there isn't a header
            if not auth_header:
                if not self.require_account_number:
                    return None
                else:
                    raise exceptions.AuthenticationFailed

            self.assert_account_number(account_number, org_id)
        if user := self.get_user(account_number, org_id):
            return user, True
        return None


class IdentityHeaderAuthenticationUserNotRequired(IdentityHeaderAuthentication):
    """
    Authentication class that does not require a User to exist for the account number.

    This authentication checks for the identity header and requires the identity to
    exist with an account number. However, this does not require that a User matching
    the identity's account number exists.

    This variant exists because at least one public API (sysconfig) needs to have access
    restricted to an authenticated Red Hat identity before a corresponding User may have
    been created within our system.
    """

    require_account_number = True
    require_user = False
    create_user = False
