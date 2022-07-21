"""Custom DRF encoders."""
from rest_framework.utils.encoders import JSONEncoder


class JsonBytesEncoder(JSONEncoder):
    """Custom JSON encoder that converts un-decodable byte objects to "b" strings."""

    def default(self, obj):
        """Extend JSONEncoder.default to gracefully handle not-utf-8 byte objects."""
        if isinstance(obj, bytes):
            try:
                return obj.decode()
            except UnicodeDecodeError:
                return str(obj)
        else:
            return super().default(obj)
