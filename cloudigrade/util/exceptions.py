"""util.exceptions module."""
import logging

from rest_framework.exceptions import ParseError

logger = logging.getLogger(__name__)


class InvalidArn(ParseError):
    """an invalid ARN was detected."""


class NotReadyException(Exception):
    """Something was not ready and may need later retry."""

    def __init__(self, message=None):
        """Log the exception message upon creation."""
        logger.info('%s: %s', self.__class__.__name__, message)
        self.message = message


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


class AwsAutoScalingGroupNotFound(Exception):
    """The requested AutoScaling group was not found."""


class AwsNonZeroAutoScalingGroupSize(Exception):
    """Raise when AWS auto scaling group has nonzero size."""
