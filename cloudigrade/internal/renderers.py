"""Custom DRF renderers."""

from rest_framework.renderers import JSONRenderer

from internal.encoders import JsonBytesEncoder


class JsonBytesRenderer(JSONRenderer):
    """Custom JSON renderer that renders byte objects as strings."""

    encoder_class = JsonBytesEncoder
