"""Settings file meant for production like environments."""
import sentry_sdk
from django.urls import reverse
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *

IS_PRODUCTION = CLOUDIGRADE_ENVIRONMENT == "prod"

if IS_PRODUCTION and "django.contrib.admin" in DJANGO_APPS:
    # Do not allow the standard Django admin in production environments.
    DJANGO_APPS.remove("django.contrib.admin")

DJANGO_DEBUG = "False"

# CLOUDIGRADE_ENVIRONMENT may have been loaded in base.py, but if not present, it would
# have fallen back to generic defaults. However, in prod, we *require* that it be set
# explicitly. By reloading here *without* a default, we halt app startup if not present.
CLOUDIGRADE_ENVIRONMENT = env("CLOUDIGRADE_ENVIRONMENT")

SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

if isClowderEnabled():
    DATABASES["default"]["NAME"] = CLOWDER_DATABASE_NAME
    DATABASES["default"]["HOST"] = CLOWDER_DATABASE_HOST
    DATABASES["default"]["PORT"] = CLOWDER_DATABASE_PORT
    DATABASES["default"]["USER"] = CLOWDER_DATABASE_USER
    DATABASES["default"]["PASSWORD"] = CLOWDER_DATABASE_PASSWORD
else:
    DATABASES["default"]["NAME"] = env("DJANGO_DATABASE_NAME")
    DATABASES["default"]["HOST"] = env("DJANGO_DATABASE_HOST")
    DATABASES["default"]["USER"] = env("DJANGO_DATABASE_USER")
    DATABASES["default"]["PASSWORD"] = env("DJANGO_DATABASE_PASSWORD")

# Azure Settings
AZURE_CLIENT_ID = env("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = env("AZURE_CLIENT_SECRET")
AZURE_SP_OBJECT_ID = env("AZURE_SP_OBJECT_ID")
AZURE_SUBSCRIPTION_ID = env("AZURE_SUBSCRIPTION_ID")
AZURE_TENANT_ID = env("AZURE_TENANT_ID")

STATIC_ROOT = env("DJANGO_STATIC_ROOT", default="/srv/cloudigrade/static/")

if env.bool("API_ENABLE_SENTRY", default=False):
    DJANGO_SENTRY_RELEASE = (
        CLOUDIGRADE_VERSION if CLOUDIGRADE_VERSION else env("DJANGO_SENTRY_RELEASE")
    )
    DJANGO_SENTRY_SAMPLE_RATE_DEFAULT = env.float(
        "DJANGO_SENTRY_SAMPLE_RATE_DEFAULT", default=0.5
    )
    DJANGO_SENTRY_SAMPLE_RATE_BY_VIEW_NAME = json.loads(
        env.str(
            "DJANGO_SENTRY_SAMPLE_RATE_BY_VIEW_NAME",
            default='{"v2-sysconfig-list": 0.1, "health_check:health_check_home": 0.0}',
        )
    )

    def django_traces_sampler(sampling_context):
        """Determine Sentry trace sampler rate for the given context."""
        context_path = (
            sampling_context.get("wsgi_environ", {}).get("PATH_INFO", "").rstrip("/")
        )
        if not context_path:
            return DJANGO_SENTRY_SAMPLE_RATE_DEFAULT
        for view_name, sample_rate in DJANGO_SENTRY_SAMPLE_RATE_BY_VIEW_NAME.items():
            view_path = reverse(view_name).rstrip("/")
            if context_path == view_path:
                return sample_rate
        return DJANGO_SENTRY_SAMPLE_RATE_DEFAULT

    sentry_sdk.init(
        dsn=env("DJANGO_SENTRY_DSN"),
        environment=env("DJANGO_SENTRY_ENVIRONMENT"),
        release=DJANGO_SENTRY_RELEASE,
        traces_sampler=django_traces_sampler,
        integrations=[DjangoIntegration()],
        send_default_pii=True,
    )
