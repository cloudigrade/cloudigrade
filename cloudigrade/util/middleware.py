"""Custom Middleware for Cloudigrade."""
import threading
import uuid

from django.conf import settings

local = threading.local()


class RequestIDLoggingMiddleware(object):
    """Middleware to add request_id to every request."""

    def __init__(self, get_response):
        """Initialize the middleware."""
        self.get_response = get_response

    def __call__(self, request):
        """Call the middleware."""
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        self.process_request(request)

        # Call the View
        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.
        self.process_response(request, response)

        return response

    def process_request(self, request):
        """Generate a uuid for the request."""
        request_id = uuid.uuid4()
        local.request_id = request_id

    def process_response(self, request, response):
        """Add request_id to a response header."""
        response[settings.CLOUDIGRADE_REQUEST_HEADER] = local.request_id

        # Clean up the thread.
        try:
            del local.request_id
        except AttributeError:
            pass

        return response
