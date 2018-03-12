"""Custom context-specific exceptions for Cloudigrade account app."""


class InvalidCloudProviderError(RuntimeError):
    """Exception for when a report is run for an invalid cloud provider."""
