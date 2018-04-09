"""util.exceptions module."""
from rest_framework.exceptions import ParseError


class InvalidArn(ParseError):
    """an invalid ARN was detected."""

    pass


class AwsValueError(ValueError):
    """Inapropriate value given to function."""

    pass


class AwsSnapshotCopyLimitError(Exception):
    """The limit on concurrent snapshot copy operations has been met."""

    pass


class AwsSnapshotEncryptedError(Exception):
    """Raise when a snapshot is encrypted."""

    pass


class AwsSnapshotNotOwnedError(Exception):
    """Raise when our account id does not have permissions on the snapshot."""

    pass
