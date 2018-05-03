"""Custom context-specific exceptions for Cloudigrade account app."""


class InvalidCloudProviderError(RuntimeError):
    """Exception for when a report is run for an invalid cloud provider."""


class RabbitMQUnreachableError(Exception):
    """Exception for when we can't connect to RabbitMQ."""
