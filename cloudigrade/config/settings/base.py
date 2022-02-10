"""Base settings file."""
import json
import logging.config
import sys
from decimal import Decimal

import environ
from app_common_python import LoadedConfig as clowder_cfg
from app_common_python import isClowderEnabled
from boto3.session import Session


def __print(*args, **kwargs):
    """
    Print to *both* stdout *and* stderr.

    This is a horrible kludge because different OpenShift environments inconsistently
    show and preserve stdout in the pod consoles. I hope that this is only temporary,
    but I have no real expectation that OpenShift will resolve this inconsistency.

    USE THIS FUNCTION ONLY IN THIS MODULE. DO NOT LET THIS CANCER SPREAD.
    """
    stdout_args = (f"stdout: {args[0] if args else ''}",) + args[1:]
    print(*stdout_args, **kwargs)
    stderr_args = (f"stderr: {args[0] if args else ''}",) + args[1:]
    print(*stderr_args, file=sys.stderr, **kwargs)


#####################################################################
# Important settings that *must* be loaded and defined first.

ROOT_DIR = environ.Path(__file__) - 3
APPS_DIR = ROOT_DIR.path("cloudigrade")

env = environ.Env()
ENV_FILE_PATH = env("ENV_FILE_PATH", default="/mnt/secret_store/.env")
if environ.os.path.isfile(ENV_FILE_PATH):
    env.read_env(ENV_FILE_PATH)
    __print("The .env file has been loaded. See base.py for more information")

if isClowderEnabled():
    __print("Clowder: Enabled")

# Used to derive several other configs' default values later.
CLOUDIGRADE_ENVIRONMENT = env("CLOUDIGRADE_ENVIRONMENT")

# TODO refactor our app to use exclusively only one of these configs
# CLOUDIGRADE_ENVIRONMENT, AWS_NAME_PREFIX, and CLOUDTRAIL_NAME_PREFIX don't all need to
# exist since they're all basically the same; these are artifacts from older code.
AWS_NAME_PREFIX = f"{CLOUDIGRADE_ENVIRONMENT}-"
CLOUDTRAIL_NAME_PREFIX = AWS_NAME_PREFIX

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
    __print(
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
    },
}

# Extra configs for logging with Watchtower/AWS CloudWatch
CLOUDIGRADE_ENABLE_CLOUDWATCH = env.bool("CLOUDIGRADE_ENABLE_CLOUDWATCH", default=False)
CLOUDIGRADE_CW_LEVEL = env("CLOUDIGRADE_CW_LEVEL", default="INFO")
CLOUDIGRADE_CW_LOG_GROUP = env("CLOUDIGRADE_CW_LOG_GROUP", default=None)
CLOUDIGRADE_CW_STREAM_NAME = env("CLOUDIGRADE_CW_STREAM_NAME", default=None)
WATCHTOWER_USE_QUEUES = env.bool("WATCHTOWER_USE_QUEUES", default=True)
WATCHTOWER_SEND_INTERVAL = env.float("WATCHTOWER_SEND_INTERVAL", default=1.0)
WATCHTOWER_MAX_BATCH_COUNT = env.int("WATCHTOWER_MAX_BATCH_COUNT", default=1000)

if CLOUDIGRADE_ENABLE_CLOUDWATCH:
    __print("Configuring CloudWatch...")
    cw_boto3_session = Session(
        aws_access_key_id=env("CW_AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=env("CW_AWS_SECRET_ACCESS_KEY"),
        region_name=env("CW_AWS_REGION_NAME"),
    )
    LOGGING["handlers"]["watchtower"] = {
        "level": CLOUDIGRADE_CW_LEVEL,
        "class": "watchtower.CloudWatchLogHandler",
        "boto3_session": cw_boto3_session,
        "log_group": CLOUDIGRADE_CW_LOG_GROUP,
        "stream_name": CLOUDIGRADE_CW_STREAM_NAME,
        "formatter": "verbose",
        "use_queues": WATCHTOWER_USE_QUEUES,
        "send_interval": WATCHTOWER_SEND_INTERVAL,
        "max_batch_count": WATCHTOWER_MAX_BATCH_COUNT,
    }
    for logger_name, logger in LOGGING["loggers"].items():
        __print(f"Appending watchtower to handlers for '{logger_name}'")
        logger["handlers"].append("watchtower")
    __print("Configured CloudWatch.")
    __print(f"LOGGING with CloudWatch is {LOGGING}")

# Important note: dictConfig must happen *after* adding the Watchtower handlers above.
logging.config.dictConfig(LOGGING)

#####################################################################
# AWS S3 (file buckets)

S3_DEFAULT_REGION = env("S3_DEFAULT_REGION", default="us-east-1")

# S3 configs for buckets that handle customer CloudTrail logs
AWS_S3_BUCKET_NAME = f"{AWS_NAME_PREFIX}cloudigrade-trails"
AWS_S3_BUCKET_LC_NAME = env("AWS_S3_BUCKET_LC_NAME", default="s3_lifecycle_policy")
AWS_S3_BUCKET_LC_IA_TRANSITION = env.int("AWS_S3_BUCKET_LC_IA_TRANSITION", default=30)
AWS_S3_BUCKET_LC_GLACIER_TRANSITION = env.int(
    "AWS_S3_BUCKET_LC_GLACIER_TRANSITION", default=60
)
AWS_S3_BUCKET_LC_MAX_AGE = env.int("AWS_S3_BUCKET_LC_MAX_AGE", default=1460)

#####################################################################
# AWS SQS (Cloudtrail Notifications)
#
# This AWS_CLOUDTRAIL_EVENT_URL has a placeholder where an AWS Account ID should be.
# That placeholder "000000000000" value is okay for tests but *must* be overridden when
# actually running cloudigrade, such as in local.py and prod.py.
AWS_CLOUDTRAIL_EVENT_URL = (
    f"https://sqs.us-east-1.amazonaws.com/"
    f"000000000000/{CLOUDIGRADE_ENVIRONMENT}-cloudigrade-cloudtrail-s3"
)
AWS_DEFAULT_REGION = env("AWS_DEFAULT_REGION", default="us-east-1")
SQS_DEFAULT_REGION = env("SQS_DEFAULT_REGION", default=AWS_DEFAULT_REGION)
AWS_SQS_MAX_HOUNDI_YIELD_COUNT = env.int("AWS_SQS_MAX_HOUNDI_YIELD_COUNT", default=10)
AWS_SQS_MAX_RECEIVE_COUNT = env.int("AWS_SQS_MAX_RECEIVE_COUNT", default=5)
AWS_SQS_MAX_YIELD_COUNT = env.int("AWS_SQS_MAX_YIELD_COUNT", default=25)

#####################################################################
# Configs used for running houndigrade and accessing its results

HOUNDIGRADE_ECS_IMAGE_NAME = env(
    "HOUNDIGRADE_ECS_IMAGE_NAME", default="cloudigrade/houndigrade"
)
HOUNDIGRADE_ECS_IMAGE_TAG = env("HOUNDIGRADE_ECS_IMAGE_TAG", default="latest")
HOUNDIGRADE_RESULTS_QUEUE_NAME = f"{CLOUDIGRADE_ENVIRONMENT}-cloudigrade-inspections-s3"
HOUNDIGRADE_RESULTS_BUCKET_NAME = f"{CLOUDIGRADE_ENVIRONMENT}-cloudigrade-inspections"
HOUNDIGRADE_SENTRY_DSN = env("HOUNDIGRADE_SENTRY_DSN", default="")
HOUNDIGRADE_SENTRY_RELEASE = (
    HOUNDIGRADE_ECS_IMAGE_TAG
    if HOUNDIGRADE_ECS_IMAGE_TAG
    else env("HOUNDIGRADE_SENTRY_RELEASE", default="")
)
HOUNDIGRADE_SENTRY_ENVIRONMENT = env("HOUNDIGRADE_SENTRY_ENVIRONMENT", default="")

#####################################################################
# Redis (message queues)

if isClowderEnabled():
    REDIS_USERNAME = clowder_cfg.inMemoryDb.username
    REDIS_PASSWORD = clowder_cfg.inMemoryDb.password
    REDIS_HOST = clowder_cfg.inMemoryDb.hostname
    REDIS_PORT = clowder_cfg.inMemoryDb.port
    __print(f"Clowder: Redis: {REDIS_HOST}:{REDIS_PORT}")
else:
    REDIS_USERNAME = env("REDIS_USERNAME", default="")
    REDIS_PASSWORD = env("REDIS_PASSWORD", default="")
    REDIS_HOST = env("REDIS_HOST", default="localhost")
    REDIS_PORT = env.int("REDIS_PORT", default=6379)

REDIS_AUTH = f"{REDIS_USERNAME or ''}:{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
REDIS_URL = f"redis://{REDIS_AUTH}{REDIS_HOST}:{REDIS_PORT}"

#####################################################################
# Celery broker

CELERY_BROKER_TRANSPORT_OPTIONS = {
    "global_keyprefix": AWS_NAME_PREFIX,
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_BROKER_USE_SSL = None
CELERY_REDIS_BACKEND_USE_SSL = CELERY_BROKER_USE_SSL
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
    "api.tasks.fix_problematic_runs": {"queue": "fix_problematic_runs"},
    "api.tasks.inspect_pending_images": {"queue": "inspect_pending_images"},
    "api.tasks.notify_application_availability_task": {
        "queue": "notify_application_availability_task"
    },
    "api.tasks.persist_inspection_cluster_results_task": {
        "queue": "persist_inspection_cluster_results_task"
    },
    "api.tasks.recalculate_concurrent_usage_for_all_users": {
        "queue": "recalculate_concurrent_usage_for_all_users"
    },
    "api.tasks.recalculate_concurrent_usage_for_user_id": {
        "queue": "recalculate_concurrent_usage_for_user_id"
    },
    "api.tasks.recalculate_concurrent_usage_for_user_id_on_date": {
        "queue": "recalculate_concurrent_usage_for_user_id_on_date"
    },
    "api.tasks.recalculate_runs_for_all_cloud_accounts": {
        "queue": "recalculate_runs_for_all_cloud_accounts"
    },
    "api.tasks.recalculate_runs_for_cloud_account_id": {
        "queue": "recalculate_runs_for_cloud_account_id"
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
    # api.clouds.aws.tasks
    "api.clouds.aws.tasks.analyze_log": {"queue": "analyze_log"},
    "api.clouds.aws.tasks.configure_customer_aws_and_create_cloud_account": {
        "queue": "configure_customer_aws_and_create_cloud_account"
    },
    "api.clouds.aws.tasks.copy_ami_snapshot": {"queue": "copy_ami_snapshot"},
    "api.clouds.aws.tasks.copy_ami_to_customer_account": {
        "queue": "copy_ami_to_customer_account"
    },
    "api.clouds.aws.tasks.delete_snapshot": {"queue": "delete_snapshot"},
    "api.clouds.aws.tasks.initial_aws_describe_instances": {
        "queue": "initial_aws_describe_instances"
    },
    "api.clouds.aws.tasks.launch_inspection_instance": {
        "queue": "launch_inspection_instance"
    },
    "api.clouds.aws.tasks.remove_snapshot_ownership": {
        "queue": "remove_snapshot_ownership"
    },
    "api.clouds.aws.tasks.repopulate_ec2_instance_mapping": {
        "queue": "repopulate_ec2_instance_mapping"
    },
    # api.clouds.azure.tasks
    "api.clouds.azure.tasks.repopulate_azure_instance_mapping": {
        "queue": "repopulate_azure_instance_mapping"
    },
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

MAX_ALLOWED_INSPECTION_ATTEMPTS = env.int("MAX_ALLOWED_INSPECTION_ATTEMPTS", default=5)

INSPECT_PENDING_IMAGES_MIN_AGE = env.int(
    "INSPECT_PENDING_IMAGES_MIN_AGE", default=60 * 60 * 12  # 12 hours
)

# Limit in seconds for how long we expect the inspection snapshots to exist.
INSPECTION_SNAPSHOT_CLEAN_UP_INITIAL_DELAY = env.int(
    "INSPECTION_SNAPSHOT_CLEAN_UP_INITIAL_DELAY", default=60 * 60
)  # 1 hour
INSPECTION_SNAPSHOT_CLEAN_UP_RETRY_DELAY = env.int(
    "INSPECTION_SNAPSHOT_CLEAN_UP_RETRY_DELAY", default=60 * 30
)  # 30 minutes

DELETE_INACTIVE_USERS_MIN_AGE = env.int(
    "DELETE_INACTIVE_USERS_MIN_AGE", default=60 * 60 * 24
)

# Cache ttl settings
CACHE_TTL_DEFAULT = env.int("CACHE_TTL_DEFAULT", default=60)

CACHE_TTL_SOURCES_APPLICATION_TYPE_ID = env.int(
    "CACHE_TTL_SOURCES_APPLICATION_TYPE_ID", default=CACHE_TTL_DEFAULT
)

# How far back should we look for related data when recalculating runs
RECALCULATE_RUNS_SINCE_DAYS_AGO = env.int("RECALCULATE_RUNS_SINCE_DAYS_AGO", default=3)
# How far back should we look for related data when recalculating concurrent usage
RECALCULATE_CONCURRENT_USAGE_SINCE_DAYS_AGO = env.int(
    "RECALCULATE_CONCURRENT_USAGE_SINCE_DAYS_AGO", default=3
)

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

#####################################################################
# Kafka

# TODO: Rename "LISTENER" variables with more general-purpose names.
# Originally, cloudigrade only read messages from Kafka, but now it also produces them,
# and the "LISTENER" nomenclature is leftover from an older version of its code.

# Sources/Kafka Listener Values
LISTENER_TOPIC = env("LISTENER_TOPIC", default="platform.sources.event-stream")
LISTENER_GROUP_ID = env("LISTENER_GROUP_ID", default="cloudmeter_ci")

if isClowderEnabled():
    kafka_broker = clowder_cfg.kafka.brokers[0]
    LISTENER_SERVER = kafka_broker.hostname
    LISTENER_PORT = kafka_broker.port
    __print(f"Clowder: Listener server: {LISTENER_SERVER}:{LISTENER_PORT}")
else:
    LISTENER_SERVER = env(
        "LISTENER_SERVER", default="platform-mq-ci-kafka-bootstrap.platform-mq-ci.svc"
    )
    LISTENER_PORT = env.int("LISTENER_PORT", default=9092)

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
)
if isClowderEnabled():
    CLOWDER_SOURCES_API_BASE_URL = ""
    for endpoint in clowder_cfg.endpoints:
        if endpoint.app == "sources-api":
            CLOWDER_SOURCES_API_BASE_URL = f"http://{endpoint.hostname}:{endpoint.port}"
    if CLOWDER_SOURCES_API_BASE_URL == "":
        __print(
            f"Clowder: Sources api service was not found, "
            f"using default url: {SOURCES_API_BASE_URL}"
        )
    else:
        SOURCES_API_BASE_URL = CLOWDER_SOURCES_API_BASE_URL
        __print(f"Clowder: Sources api service url: {SOURCES_API_BASE_URL}")

SOURCES_PSK = env("SOURCES_PSK", default="")

SOURCE_API_INTERNAL_URI = "/internal/v1.0/"
SOURCES_API_EXTERNAL_URI = "/api/sources/v3.0/"

SOURCES_CLOUDMETER_ARN_AUTHTYPE = "cloud-meter-arn"
SOURCES_CLOUDMETER_LIGHTHOUSE_AUTHTYPE = "lighthouse_subscription_id"
SOURCES_CLOUDMETER_AUTHTYPES = (
    SOURCES_CLOUDMETER_ARN_AUTHTYPE,
    SOURCES_CLOUDMETER_LIGHTHOUSE_AUTHTYPE,
)
SOURCES_RESOURCE_TYPE = "Application"

# Sources Availability Check Values
SOURCES_STATUS_TOPIC = env("SOURCES_STATUS_TOPIC", default="platform.sources.status")
SOURCES_AVAILABILITY_EVENT_TYPE = env(
    "SOURCES_AVAILABILITY_EVENT_TYPE", default="availability_status"
)

#####################################################################
