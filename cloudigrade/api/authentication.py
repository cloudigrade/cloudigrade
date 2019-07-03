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


class ThreeScaleAuthentication(BaseAuthentication):
    """
    3scale authentication.

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

        """
        insights_request_id = request.META.get(
            settings.INSIGHTS_REQUEST_ID_HEADER, None
        )
        logger.info(
            _('Authenticating via insights, INSIGHTS_REQUEST_ID: %s'),
            insights_request_id
        )

        auth_header = request.META.get(settings.INSIGHTS_IDENTITY_HEADER, None)

        # Can't authenticate if there isn't a header
        if not auth_header:
            return None
        try:
            auth = json.loads(
                base64.b64decode(auth_header).decode(HTTP_HEADER_ENCODING)
            )

        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.info(
                _('Authentication Failed: 3scale header parsing error %s'), e
            )
            raise exceptions.AuthenticationFailed(
                _('Invalid 3scale header: {error}').format(error=e)
            )

        # If account_number is not in header, authentication fails
        try:
            account_number = auth['identity']['account_number']
        except KeyError:
            logger.info(
                _('Authentication Failed: '
                  'account_number not contained '
                  'in 3scale header %s.'), auth_header
            )
            raise exceptions.AuthenticationFailed(
                _('Invalid 3scale header: missing user account_number field')
            )

        user, created = User.objects.get_or_create(username=account_number)
        if created:
            user.set_unusable_password()
            logger.info(
                _('User %s was not found and has been created.'),
                account_number,
            )
        return user, True
