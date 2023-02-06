"""Base settings file."""
import json
import logging.config
import sys
from decimal import Decimal

import boto3
import environ
from app_common_python import LoadedConfig as clowder_cfg
from app_common_python import isClowderEnabled


def __print_stderr(*args, **kwargs):
    """Print to stderr."""
    kwargs["file"] = sys.stderr
    print(*args, **kwargs)


#####################################################################
# Important settings that *must* be loaded and defined first.

ROOT_DIR = environ.Path(__file__) - 3
APPS_DIR = ROOT_DIR.path("cloudigrade")

env = environ.Env()
ENV_FILE_PATH = env("ENV_FILE_PATH", default="/mnt/secret_store/.env")
if environ.os.path.isfile(ENV_FILE_PATH):
    env.read_env(ENV_FILE_PATH)
    __print_stderr("The .env file has been loaded. See base.py for more information")

if isClowderEnabled():
    __print_stderr("Clowder: Enabled")

# Used to derive several other configs' default values later.
CLOUDIGRADE_ENVIRONMENT = env("CLOUDIGRADE_ENVIRONMENT")

# TODO refactor our app to use exclusively only one of these configs
# CLOUDIGRADE_ENVIRONMENT and AWS_NAME_PREFIX don't both need to
# exist since they're all basically the same; these are artifacts from older code.
AWS_NAME_PREFIX = f"{CLOUDIGRADE_ENVIRONMENT}-"

#####################################################################
# Standard Django project configs

# Important Security Settings
SECRET_KEY = env("DJANGO_SECRET_KEY", default="base")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", default=["*"])

# Azure Settings
AZURE_CLIENT_ID = env("AZURE_CLIENT_ID", default="azure-client-id")
AZURE_CLIENT_SECRET = env("AZURE_CLIENT_SECRET", default="very-secret-much-secure")
AZURE_SP_OBJECT_ID = env("AZURE_SP_OBJECT_ID", default="azure-sp-object-id")
AZURE_SUBSCRIPTION_ID = env("AZURE_SUBSCRIPTION_ID", default="azure-subscription-id")
AZURE_TENANT_ID = env("AZURE_TENANT_ID", default="azure-tenant-id")

# Default apps go here
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

# Any pip installed apps will go here
THIRD_PARTY_APPS = [
    "django_celery_beat",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "django_prometheus",
    "django_redis",
    "generic_relations",
    "health_check",
    "health_check.db",
]

# Apps specific to this project go here
LOCAL_APPS = [
    "util.apps.UtilConfig",
    "api.apps.ApiConfig",
    "internal.apps.InternalConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# The AUTH_USER_MODEL for Django can't be easily switched mid-project
# with migrations. Keeping this commented out for now.
# AUTH_USER_MODEL = "api.User"

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",  # should always be first
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "util.middleware.RequestIDLoggingMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",  # should always be last
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases
DATABASES = {
    "default": {
        "ATOMIC_REQUESTS": env("DJANGO_ATOMIC_REQUESTS", default=True),
        "ENGINE": env(
            "DJANGO_DATABASE_ENGINE", default="django_prometheus.db.backends.postgresql"
        ),
        "CONN_MAX_AGE": env.int("DJANGO_DATABASE_CONN_MAX_AGE", default=0),
    }
}

if isClowderEnabled():
    CLOWDER_DATABASE_NAME = clowder_cfg.database.name
    CLOWDER_DATABASE_HOST = clowder_cfg.database.hostname
    CLOWDER_DATABASE_PORT = clowder_cfg.database.port
    CLOWDER_DATABASE_USER = clowder_cfg.database.username
    CLOWDER_DATABASE_PASSWORD = clowder_cfg.database.password

    # with postigrade deployed in clowder, we need to hit its endpoint
    # hostname and webPort instead.
    for endpoint in clowder_cfg.endpoints:
        if endpoint.app == "postigrade" and endpoint.name == "svc":
            CLOWDER_DATABASE_HOST = endpoint.hostname
            CLOWDER_DATABASE_PORT = endpoint.port

if isClowderEnabled():
    DATABASES["default"] = {
        **DATABASES["default"],
        **{
            "NAME": CLOWDER_DATABASE_NAME,
            "HOST": CLOWDER_DATABASE_HOST,
            "PORT": CLOWDER_DATABASE_PORT,
            "USER": CLOWDER_DATABASE_USER,
            "PASSWORD": CLOWDER_DATABASE_PASSWORD,
        },
    }
    __print_stderr(
        f"Clowder: Database name: {CLOWDER_DATABASE_NAME} "
        f"host: {CLOWDER_DATABASE_HOST}:{CLOWDER_DATABASE_PORT}"
    )
else:
    DATABASES["default"] = {
        **DATABASES["default"],
        **{
            "NAME": env("DJANGO_DATABASE_NAME", default="postgres"),
            "HOST": env("DJANGO_DATABASE_HOST", default="localhost"),
            "USER": env("DJANGO_DATABASE_USER", default="postgres"),
            "PASSWORD": env("DJANGO_DATABASE_PASSWORD", default="postgres"),
            "PORT": env.int("DJANGO_DATABASE_PORT", default=5432),
        },
    }

# New in Django 3.2:
# 3.1 and older default is 32-bit AutoField. 3.2 now recommends 64-bit BigAutoField.
# See "Customizing type of auto-created primary keys" in the 3.2 release notes:
# https://docs.djangoproject.com/en/3.2/releases/3.2/
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Password validation
# https://docs.djangoproject.com/en/2.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",  # noqa: E501
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_URL = env("DJANGO_STATIC_URL", default="/static/")
STATIC_ROOT = env("DJANGO_STATIC_ROOT", default=str(ROOT_DIR.path("static")))

# Django Rest Framework
# http://www.django-rest-framework.org/api-guide/settings/

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "drf_insights_pagination.pagination.InsightsPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "api.authentication.IdentityHeaderAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # https://www.django-rest-framework.org/api-guide/renderers/#setting-the-renderers
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "util.exceptions.api_exception_handler",
}

#####################################################################
# Logging
# https://docs.djangoproject.com/en/3.2/topics/logging/
# https://docs.python.org/3.8/library/logging.html
# https://www.caktusgroup.com/blog/2015/01/27/Django-Logging-Configuration-logging_config-default-settings-logger/  # noqa:E501
LOGGING_CONFIG = None
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "util.logfilter.RequestIDFilter"}},
    "formatters": {
        "verbose": {
            "format": "%(asctime)s | %(levelname)s | "
            "%(process)s | "
            "%(filename)s:%(funcName)s:%(lineno)d | "
            "requestid:%(request_id)s | %(message)s"
        },
    },
    "handlers": {
        "console": {
            "level": env("DJANGO_CONSOLE_LOG_LEVEL", default="INFO"),
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["request_id"],
        },
    },
    "loggers": {
        "": {
            "handlers": [
                "console",
            ],
            "level": env("DJANGO_ALL_LOG_LEVEL", default="INFO"),
        },
        "api": {
            "handlers": [
                "console",
            ],
            "level": env("CLOUDIGRADE_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "config": {
            "handlers": [
                "console",
            ],
            "level": env("CLOUDIGRADE_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "internal": {
            "handlers": [
                "console",
            ],
            "level": env("CLOUDIGRADE_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "util": {
            "handlers": [
                "console",
            ],
            "level": env("CLOUDIGRADE_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "django": {
            "handlers": [
                "console",
            ],
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "azure": {
            "handlers": [
                "console",
            ],
            "level": env("AZURE_LOG_LEVEL", default="WARNING"),
            "propagate": False,
        },
    },
}

# Extra configs for logging with Watchtower/AWS CloudWatch
CLOUDIGRADE_ENABLE_CLOUDWATCH = env.bool("CLOUDIGRADE_ENABLE_CLOUDWATCH", default=False)
CLOUDIGRADE_CW_LEVEL = env("CLOUDIGRADE_CW_LEVEL", default="INFO")
CLOUDIGRADE_CW_LOG_GROUP = env("CLOUDIGRADE_CW_LOG_GROUP", default=None)
CLOUDIGRADE_CW_STREAM_NAME = env("CLOUDIGRADE_CW_STREAM_NAME", default=None)
CLOUDIGRADE_CW_RETENTION_DAYS = env.int("CLOUDIGRADE_CW_RETENTION_DAYS", default=None)
WATCHTOWER_USE_QUEUES = env.bool("WATCHTOWER_USE_QUEUES", default=True)
WATCHTOWER_SEND_INTERVAL = env.float("WATCHTOWER_SEND_INTERVAL", default=1.0)
WATCHTOWER_MAX_BATCH_COUNT = env.int("WATCHTOWER_MAX_BATCH_COUNT", default=1000)

if CLOUDIGRADE_ENABLE_CLOUDWATCH:
    __print_stderr("Configuring CloudWatch...")
    cw_boto3_client = boto3.client(
        "logs",
        aws_access_key_id=env("CW_AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=env("CW_AWS_SECRET_ACCESS_KEY"),
        region_name=env("CW_AWS_REGION_NAME"),
    )
    LOGGING["handlers"]["watchtower"] = {
        "level": CLOUDIGRADE_CW_LEVEL,
        "class": "watchtower.CloudWatchLogHandler",
        "boto3_client": cw_boto3_client,
        "log_group_name": CLOUDIGRADE_CW_LOG_GROUP,
        "log_stream_name": CLOUDIGRADE_CW_STREAM_NAME,
        "log_group_retention_days": CLOUDIGRADE_CW_RETENTION_DAYS,
        "formatter": "verbose",
        "use_queues": WATCHTOWER_USE_QUEUES,
        "send_interval": WATCHTOWER_SEND_INTERVAL,
        "max_batch_count": WATCHTOWER_MAX_BATCH_COUNT,
    }
    for logger_name, logger in LOGGING["loggers"].items():
        __print_stderr(f"Appending watchtower to handlers for '{logger_name}'")
        logger["handlers"].append("watchtower")
    __print_stderr("Configured CloudWatch.")
    __print_stderr(f"LOGGING with CloudWatch is {LOGGING}")

# Important note: dictConfig must happen *after* adding the Watchtower handlers above.
logging.config.dictConfig(LOGGING)

#####################################################################
# Redis (message queues)

if isClowderEnabled():
    REDIS_USERNAME = clowder_cfg.inMemoryDb.username
    REDIS_PASSWORD = clowder_cfg.inMemoryDb.password
    REDIS_HOST = clowder_cfg.inMemoryDb.hostname
    REDIS_PORT = clowder_cfg.inMemoryDb.port
    __print_stderr(f"Clowder: Redis: {REDIS_HOST}:{REDIS_PORT}")
else:
    REDIS_USERNAME = env("REDIS_USERNAME", default="")
    REDIS_PASSWORD = env("REDIS_PASSWORD", default="")
    REDIS_HOST = env("REDIS_HOST", default="localhost")
    REDIS_PORT = env.int("REDIS_PORT", default=6379)

REDIS_AUTH = f"{REDIS_USERNAME or ''}:{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
REDIS_URL = f"redis://{REDIS_AUTH}{REDIS_HOST}:{REDIS_PORT}"
REDIS_HEALTH_CHECK_INTERVAL = env.int("REDIS_HEALTH_CHECK_INTERVAL", default=30)

#####################################################################
# Celery broker

CELERY_BROKER_TRANSPORT_OPTIONS = {
    "global_keyprefix": AWS_NAME_PREFIX,
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_BROKER_USE_SSL = None
CELERY_REDIS_BACKEND_USE_SSL = CELERY_BROKER_USE_SSL
CELERY_REDIS_BACKEND_HEALTH_CHECK_INTERVAL = REDIS_HEALTH_CHECK_INTERVAL
CELERY_ACCEPT_CONTENT = ["json", "pickle"]

#####################################################################
# Celery tasks

# Warning: setting Celery's "eager" option is intended only for local development.
# Setting this to "True" means Celery will never enqueue task messages for processing.
# Instead it will always act as though the task function was called *directly*, and that
# will block the current thread while the task function executes synchronously.
# See also Celery docs:
# https://docs.celeryproject.org/en/stable/userguide/configuration.html#std-setting-task_always_eager  # noqa:E501
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)

CELERY_TASK_ROUTES = {
    # api.tasks
    "api.tasks.delete_cloud_account": {"queue": "delete_cloud_account"},
    "api.tasks.enable_account": {"queue": "enable_account"},
    "api.tasks.delete_inactive_users": {"queue": "delete_inactive_users"},
    "api.tasks.delete_cloud_accounts_not_in_sources": {
        "queue": "delete_cloud_accounts_not_in_sources"
    },
    "api.tasks.delete_orphaned_cloud_accounts": {
        "queue": "delete_orphaned_cloud_accounts"
    },
    "api.tasks.migrate_account_numbers_to_org_ids": {
        "queue": "migrate_account_numbers_to_org_ids"
    },
    "api.tasks.notify_application_availability_task": {
        "queue": "notify_application_availability_task"
    },
    "api.tasks.check_and_cache_sqs_queues_lengths": {
        "queue": "check_and_cache_sqs_queues_lengths"
    },
    # api.tasks supporting source kafka message handling
    "api.tasks.create_from_sources_kafka_message": {
        "queue": "create_from_sources_kafka_message"
    },
    "api.tasks.delete_from_sources_kafka_message": {
        "queue": "delete_from_sources_kafka_message"
    },
    "api.tasks.update_from_sources_kafka_message": {
        "queue": "update_from_sources_kafka_message"
    },
    "api.tasks.pause_from_sources_kafka_message": {
        "queue": "pause_from_sources_kafka_message"
    },
    "api.tasks.unpause_from_sources_kafka_message": {
        "queue": "unpause_from_sources_kafka_message"
    },
    # api.tasks supporting synthetic data generation
    "api.tasks.delete_expired_synthetic_data": {
        "queue": "delete_expired_synthetic_data"
    },
    # api.clouds.aws.tasks
    "api.clouds.aws.tasks.configure_customer_aws_and_create_cloud_account": {
        "queue": "configure_customer_aws_and_create_cloud_account"
    },
    # api.clouds.azure.tasks
    "api.clouds.azure.tasks.check_azure_subscription_and_create_cloud_account": {
        "queue": "check_azure_subscription_and_create_cloud_account"
    },
}

#####################################################################
# cloudigrade various configs

IS_PRODUCTION = False

CLOUDIGRADE_VERSION = env("IMAGE_TAG", default=env("CLOUDIGRADE_VERSION", default=None))

# TODO Should this really be in settings? Consider moving to an AWS-specific module.
RHEL_IMAGES_AWS_ACCOUNTS = [
    Decimal("841258680906"),  # china
    Decimal("219670896067"),  # govcloud
    Decimal("309956199498"),  # all others
]

DELETE_INACTIVE_USERS_MIN_AGE = env.int(
    "DELETE_INACTIVE_USERS_MIN_AGE", default=60 * 60 * 24
)

#####################################################################
# Django caching

# Cache ttl settings
CACHE_TTL_DEFAULT = env.int("CACHE_TTL_DEFAULT", default=60)

CACHE_TTL_SOURCES_APPLICATION_TYPE_ID = env.int(
    "CACHE_TTL_SOURCES_APPLICATION_TYPE_ID", default=CACHE_TTL_DEFAULT
)

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": f"{CLOUDIGRADE_ENVIRONMENT}-cloudigrade",
        "TIMEOUT": CACHE_TTL_DEFAULT,
        "OPTIONS": {
            "CONNECTION_POOL_KWARGS": {
                "health_check_interval": REDIS_HEALTH_CHECK_INTERVAL
            }
        },
    },
    "locmem": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}

# How far back should we look for orphaned CloudAccounts to delete
DELETE_ORPHANED_ACCOUNTS_UPDATED_MORE_THAN_SECONDS_AGO = env.int(
    "DELETE_ORPHANED_ACCOUNTS_UPDATED_MORE_THAN_SECONDS_AGO", default=5 * 60
)

# How far back should we look for CloudAccounts not in sources to delete
DELETE_CLOUD_ACCOUNTS_NOT_IN_SOURCES_UPDATED_MORE_THAN_SECONDS_AGO = env.int(
    "DELETE_CLOUD_ACCOUNTS_NOT_IN_SOURCES_UPDATED_MORE_THAN_SECONDS_AGO", default=5 * 60
)

#####################################################################
# cloudigrade authentication-related configs

VERBOSE_INSIGHTS_IDENTITY_HEADER_LOGGING = env.bool(
    "VERBOSE_INSIGHTS_IDENTITY_HEADER_LOGGING", default=False
)
VERBOSE_SOURCES_NOTIFICATION_LOGGING = env.bool(
    "VERBOSE_SOURCES_NOTIFICATION_LOGGING", default=False
)
CLOUDIGRADE_PSKS_JSON = env("CLOUDIGRADE_PSKS", default="{}")
CLOUDIGRADE_PSKS = dict(json.loads(CLOUDIGRADE_PSKS_JSON))

# Various HEADER names
CLOUDIGRADE_REQUEST_HEADER = "X-CLOUDIGRADE-REQUEST-ID"
INSIGHTS_REQUEST_ID_HEADER = "HTTP_X_RH_INSIGHTS_REQUEST_ID"
INSIGHTS_IDENTITY_HEADER = "HTTP_X_RH_IDENTITY"
INSIGHTS_INTERNAL_FAKE_IDENTITY_HEADER = "HTTP_X_RH_INTERNAL_FAKE_IDENTITY"
CLOUDIGRADE_PSK_HEADER = "HTTP_X_RH_CLOUDIGRADE_PSK"
CLOUDIGRADE_ACCOUNT_NUMBER_HEADER = "HTTP_X_RH_CLOUDIGRADE_ACCOUNT_NUMBER"
CLOUDIGRADE_ORG_ID_HEADER = "HTTP_X_RH_CLOUDIGRADE_ORG_ID"

#####################################################################
# Kafka

# Sometimes we have to fetch the Kafka topic names from Clowder.
# Sometimes the topic name we think we want (requestedName) isn't what we get (name).
# Yes, it's complicated. I'd love to clean up and simplify this later.
# Can just stop using the environment variables entirely? TODO Deal with this later.

# Default values assuming Clowder isn't present.
KAFKA_TOPIC_NAMES = {
    "platform.sources.event-stream": env(
        "LISTENER_TOPIC", default="platform.sources.event-stream"
    ),
    "platform.sources.status": env(
        "SOURCES_STATUS_TOPIC", default="platform.sources.status"
    ),
}
if isClowderEnabled():
    topics = clowder_cfg.kafka.topics
    clowder_topic_names = {(topic.requestedName, topic.name) for topic in topics}
    # Override our defaults with whatever Clowder provided.
    KAFKA_TOPIC_NAMES.update(clowder_topic_names)


# Sources/Kafka Listener Values
LISTENER_TOPIC = KAFKA_TOPIC_NAMES["platform.sources.event-stream"]
LISTENER_GROUP_ID = env("LISTENER_GROUP_ID", default="cloudmeter_ci")

KAFKA_SERVER_CA_LOCATION = None
KAFKA_SERVER_SECURITY_PROTOCOL = None
KAFKA_SERVER_SASL_MECHANISM = None
KAFKA_SERVER_SASL_USERNAME = None
KAFKA_SERVER_SASL_PASSWORD = None
KAFKA_LISTENER_ADDRESS_FAMILY = env("KAFKA_LISTENER_ADDRESS_FAMILY", default="any")

if isClowderEnabled():
    kafka_broker = clowder_cfg.kafka.brokers[0]
    KAFKA_SERVER_HOST = kafka_broker.hostname
    KAFKA_SERVER_PORT = kafka_broker.port
    __print_stderr(f"Clowder: Kafka server: {KAFKA_SERVER_HOST}:{KAFKA_SERVER_PORT}")
    if kafka_broker.cacert:
        KAFKA_SERVER_CA_LOCATION = clowder_cfg.kafka_ca()
        __print_stderr("Clowder: Kafka server CA defined")

    if kafka_broker.sasl and kafka_broker.sasl.username:
        KAFKA_SERVER_SECURITY_PROTOCOL = kafka_broker.sasl.securityProtocol
        KAFKA_SERVER_SASL_MECHANISM = kafka_broker.sasl.saslMechanism
        KAFKA_SERVER_SASL_USERNAME = kafka_broker.sasl.username
        KAFKA_SERVER_SASL_PASSWORD = kafka_broker.sasl.password
        __print_stderr("Clowder: Kafka server SASL enabled")
else:
    KAFKA_SERVER_HOST = env(
        "KAFKA_SERVER_HOST", default="platform-mq-ci-kafka-bootstrap.platform-mq-ci.svc"
    )
    KAFKA_SERVER_PORT = env.int("KAFKA_SERVER_PORT", default=9092)

#####################################################################
# Sources API integration

SOURCES_ENABLE_DATA_MANAGEMENT = env.bool(
    "SOURCES_ENABLE_DATA_MANAGEMENT", default=True
)
SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA = env.bool(
    "SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA", default=True
)


SOURCES_API_BASE_URL = env(
    "SOURCES_API_BASE_URL", default="http://sources-api.sources-ci.svc:8080"
).rstrip("/")
if isClowderEnabled():
    CLOWDER_SOURCES_API_BASE_URL = ""
    for endpoint in clowder_cfg.endpoints:
        if endpoint.app == "sources-api":
            CLOWDER_SOURCES_API_BASE_URL = f"http://{endpoint.hostname}:{endpoint.port}"
    if CLOWDER_SOURCES_API_BASE_URL == "":
        __print_stderr(
            f"Clowder: Sources api service was not found, "
            f"using default url: {SOURCES_API_BASE_URL}"
        )
    else:
        SOURCES_API_BASE_URL = CLOWDER_SOURCES_API_BASE_URL
        __print_stderr(f"Clowder: Sources api service url: {SOURCES_API_BASE_URL}")

SOURCES_PSK = env("SOURCES_PSK", default="")

SOURCES_API_INTERNAL_BASE_URL = f"{SOURCES_API_BASE_URL}/internal/v1.0"
SOURCES_API_EXTERNAL_BASE_URL = f"{SOURCES_API_BASE_URL}/api/sources/v3.0"

SOURCES_CLOUDMETER_ARN_AUTHTYPE = "cloud-meter-arn"
SOURCES_CLOUDMETER_LIGHTHOUSE_AUTHTYPE = "lighthouse_subscription_id"
SOURCES_CLOUDMETER_AUTHTYPES = (
    SOURCES_CLOUDMETER_ARN_AUTHTYPE,
    SOURCES_CLOUDMETER_LIGHTHOUSE_AUTHTYPE,
)
SOURCES_RESOURCE_TYPE = "Application"

# Sources Availability Check Values
SOURCES_STATUS_TOPIC = KAFKA_TOPIC_NAMES["platform.sources.status"]
SOURCES_AVAILABILITY_EVENT_TYPE = env(
    "SOURCES_AVAILABILITY_EVENT_TYPE", default="availability_status"
)

#####################################################################
# Org ID support

TENANT_TRANSLATOR_SCHEME = env("TENANT_TRANSLATOR_SCHEME", default="http")
TENANT_TRANSLATOR_HOST = env("TENANT_TRANSLATOR_HOST", default="localhost")
TENANT_TRANSLATOR_PORT = env("TENANT_TRANSLATOR_PORT", default=8892)

#####################################################################
