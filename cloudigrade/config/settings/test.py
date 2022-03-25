"""Settings file meant for running tests."""
from .base import *

DEBUG = env.bool("DJANGO_DEBUG", default=False)
SECRET_KEY = env("DJANGO_SECRET_KEY", default="test")
TEST_RUNNER = "django.test.runner.DiscoverRunner"
SOURCES_PSK = env("SOURCES_PSK", default="test")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(ROOT_DIR.path("db.sqlite3")),
    }
}

LOGGING["handlers"]["console"]["level"] = "CRITICAL"
logging.config.dictConfig(LOGGING)

# Always enable SyntheticDataRequest HTTP API for tests.
ENABLE_SYNTHETIC_DATA_REQUEST_HTTP_API = True
