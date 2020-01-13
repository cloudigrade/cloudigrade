"""Custom LogFilters for Cloudigrade."""
import logging

from util.middleware import local


class RequestIDFilter(logging.Filter):
    """Add the request_id to the context of a log record."""

    def filter(self, record):
        """Add a request_id to the record."""
        record.request_id = getattr(local, "request_id", None)
        return True
