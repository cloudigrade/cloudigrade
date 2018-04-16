"""util.exceptions module."""
from rest_framework.exceptions import ParseError


class InvalidArn(ParseError):
    """an invalid ARN was detected."""


class NotReadyException(Exception):
    """Something was not ready and may need later retry."""


class AwsSnapshotEncryptedError(Exception):
    """Raise when a snapshot is encrypted."""


class AwsSnapshotCopyLimitError(NotReadyException):
    """The limit on concurrent snapshot copy operations has been met."""


class AwsSnapshotNotOwnedError(NotReadyException):
    """Raise when our account id does not have permissions on the snapshot."""


class SnapshotNotReadyException(NotReadyException):
    """The requested snapshot was not ready."""


class AwsVolumeNotReadyError(NotReadyException):
    """The requested volume was not ready."""


class AwsVolumeError(Exception):
    """The requested volume is not in an acceptable state."""
