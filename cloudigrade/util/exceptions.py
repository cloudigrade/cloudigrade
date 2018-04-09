"""util.exceptions module."""
from rest_framework.exceptions import ParseError


class InvalidArn(ParseError):
    """an invalid ARN was detected."""


class AwsSnapshotCopyLimitError(Exception):
    """The limit on concurrent snapshot copy operations has been met."""


class AwsSnapshotEncryptedError(Exception):
    """Raise when a snapshot is encrypted."""


class AwsSnapshotNotOwnedError(Exception):
    """Raise when our account id does not have permissions on the snapshot."""


class NotReadyException(Exception):
    """Something was not ready and may need later retry."""
