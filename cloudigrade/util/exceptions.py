"""util.exceptions module."""

import http
import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework.exceptions import (
    APIException,
    NotFound,
    ParseError,
    PermissionDenied as DrfPermissionDenied,
)
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class InvalidArn(ParseError):
    """an invalid ARN was detected."""


class NotReadyException(Exception):
    """Something was not ready and may need later retry."""

    def __init__(self, message=None):
        """Log the exception message upon creation."""
        logger.info("%s: %s", self.__class__.__name__, message)
        self.message = message


class AwsThrottlingException(Exception):
    """Raise when AWS call fails because of throttling."""


# API Exceptions
class NotImplementedAPIException(APIException):
    """Raise when we encounter NotImplementedError."""

    status_code = http.HTTPStatus.NOT_IMPLEMENTED


# Sources Exceptions:
class SourcesAPIException(Exception):
    """Raise when Insights Sources API behaves unexpectedly."""


class SourcesAPINotOkStatus(SourcesAPIException):
    """Raise when Sources API returns a not-200 status."""


class SourcesAPINotJsonContent(SourcesAPIException):
    """Raise when Sources API returns not-JSON content."""


class KafkaProducerException(Exception):
    """Raise when we get an error while trying to send a Kafka message."""


def api_exception_handler(exc, context):
    """
    Log exception and return an appropriately formatted response.

    For any exception that doesn't specifically extend DRF's base APIException
    class, we deliberately suppress the original exception and raise a plain
    instance of APIException or a specific subclass of APIException. We do this
    because we do not want to leak details about the underlying error and
    system state to the end user.
    """
    if isinstance(exc, Http404):
        exc = NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = DrfPermissionDenied()
    elif isinstance(exc, NotImplementedError):
        logger.exception(exc)
        exc = NotImplementedAPIException()
    elif not isinstance(exc, APIException):
        logger.exception(exc)
        exc = APIException()
    return exception_handler(exc, context)
