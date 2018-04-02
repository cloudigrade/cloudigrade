"""util.exceptions module."""
from rest_framework.exceptions import ParseError


class InvalidArn(ParseError):
    """an invalid ARN was detected."""

    pass
