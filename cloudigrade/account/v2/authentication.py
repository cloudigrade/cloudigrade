"""Custom Cloudigrade Authentication Policies."""
import base64
import json
import logging

from django.contrib.auth.models import User
from django.utils.translation import gettext as _
from rest_framework import HTTP_HEADER_ENCODING
from rest_framework.authentication import BaseAuthentication, exceptions

logger = logging.getLogger(__name__)


class ThreeScaleAuthentication(BaseAuthentication):
    """
    3scale authentication.

    Check for the existence of a HTTP_X_RH_IDENTITY. The user identity is
    inferred based off the email in the header.
    """

    def authenticate(self, request):
        """Return a `User` if a valid `HTTP_X_RH_IDENTITY` is present."""
        auth_header = request.META.get('HTTP_X_RH_IDENTITY', None)
        # Can't authenticate if there isn't a header
        if not auth_header:
            return None
        try:
            auth = json.loads(
                base64.b64decode(auth_header).decode(HTTP_HEADER_ENCODING)
            )

        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.exception(
                _('Could not authenticate: 3scale header parsing error %s'), e
            )
            raise exceptions.AuthenticationFailed(
                _('Invalid 3scale header: {error}').format(e)
            )

        # If email is not in header, authentication fails
        try:
            email = auth['identity']['user']['email']
        except KeyError:
            return None

        user, created = User.objects.get_or_create(username=email)
        return user, True
