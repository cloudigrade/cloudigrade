"""Base settings file."""
import logging.config
import sys
from decimal import Decimal
from urllib.parse import quote

import environ
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


ROOT_DIR = environ.Path(__file__) - 3
APPS_DIR = ROOT_DIR.path("cloudigrade")

env = environ.Env()
ENV_FILE_PATH = env("ENV_FILE_PATH", default="/mnt/secret_store/.env")
if environ.os.path.isfile(ENV_FILE_PATH):
    env.read_env(ENV_FILE_PATH)
    __print("The .env file has been loaded. See base.py for more information")

# Important Security Settings
IS_PRODUCTION = False
SECRET_KEY = env("DJANGO_SECRET_KEY", default="base")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", default=["*"])

# Logging
# https://docs.djangoproject.com/en/dev/topics/logging/
# https://docs.python.org/3.6/library/logging.html
# https://www.caktusgroup.com/blog/2015/01/27/Django-Logging-Configuration-logging_config-default-settings-logger/
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

logging.config.dictConfig(LOGGING)

# AWS Defaults
S3_DEFAULT_REGION = env("S3_DEFAULT_REGION", default="us-east-1")
SQS_DEFAULT_REGION = env("SQS_DEFAULT_REGION", default="us-east-1")
HOUNDIGRADE_AWS_AVAILABILITY_ZONE = env(
    "HOUNDIGRADE_AWS_AVAILABILITY_ZONE", default="us-east-1b"
)
HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME = env(
    "HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME",
    default="EC2ContainerService-inspectigrade-EcsInstanceAsg",
)
HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE = env.int(
    "HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE", default=32
)
HOUNDIGRADE_ECS_CLUSTER_NAME = env(
    "HOUNDIGRADE_ECS_CLUSTER_NAME", default="inspectigrade-us-east-1b"
)
HOUNDIGRADE_ECS_FAMILY_NAME = env("HOUNDIGRADE_ECS_FAMILY_NAME", default="Houndigrade")
HOUNDIGRADE_ECS_IMAGE_NAME = env(
    "HOUNDIGRADE_ECS_IMAGE_NAME", default="cloudigrade/houndigrade"
)
HOUNDIGRADE_ECS_IMAGE_TAG = env("HOUNDIGRADE_ECS_IMAGE_TAG", default="latest")
HOUNDIGRADE_EXCHANGE_NAME = env("HOUNDIGRADE_EXCHANGE_NAME", default="")

RHEL_IMAGES_AWS_ACCOUNTS = [
    Decimal("841258680906"),  # china
    Decimal("219670896067"),  # govcloud
    Decimal("309956199498"),  # all others
]

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
    "generic_relations",
    "health_check",
    "health_check.db",
    "django_prometheus",
]

# Apps specific to this project go here
LOCAL_APPS = [
    "util.apps.UtilConfig",
    "api.apps.ApiConfig",
    "internal.apps.InternalConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# Middleware

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "util.middleware.RequestIDLoggingMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
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
# https://docs.djangoproject.com/en/2.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ATOMIC_REQUESTS": env("DJANGO_ATOMIC_REQUESTS", default=True),
        "ENGINE": env(
            "DJANGO_DATABASE_ENGINE",
            default="django_prometheus.db.backends.postgresql",
        ),
        "NAME": env("DJANGO_DATABASE_NAME", default="postgres"),
        "HOST": env("DJANGO_DATABASE_HOST", default="localhost"),
        "USER": env("DJANGO_DATABASE_USER", default="postgres"),
        "PASSWORD": env("DJANGO_DATABASE_PASSWORD", default="postgres"),
        "PORT": env.int("DJANGO_DATABASE_PORT", default=5432),
        "CONN_MAX_AGE": env.int("DJANGO_DATABASE_CONN_MAX_AGE", default=0),
    }
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
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
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
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/

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
    "EXCEPTION_HANDLER": "util.exceptions.api_exception_handler",
}

# Message and Task Queues

# For convenience in development environments, find defaults gracefully here.
AWS_SQS_REGION = env(
    "AWS_SQS_REGION", default=env("AWS_DEFAULT_REGION", default="us-east-1")
)

AWS_SQS_ACCESS_KEY_ID = env(
    "AWS_SQS_ACCESS_KEY_ID", default=env("AWS_ACCESS_KEY_ID", default="")
)
AWS_SQS_SECRET_ACCESS_KEY = env(
    "AWS_SQS_SECRET_ACCESS_KEY", default=env("AWS_SECRET_ACCESS_KEY", default="")
)

# We still need to ensure we have an access key and secret key for SQS.
# So, if they were not explicitly set in the environment (for example, if
# AWS_PROFILE was set instead), try to extract them from boto's session.
if not AWS_SQS_ACCESS_KEY_ID or not AWS_SQS_SECRET_ACCESS_KEY:
    import boto3

    session = boto3.Session()
    credentials = session.get_credentials()
    credentials = credentials.get_frozen_credentials()
    AWS_SQS_ACCESS_KEY_ID = credentials.access_key
    AWS_SQS_SECRET_ACCESS_KEY = credentials.secret_key

AWS_SQS_URL = env(
    "AWS_SQS_URL",
    default="sqs://{}:{}@".format(
        quote(AWS_SQS_ACCESS_KEY_ID, safe=""), quote(AWS_SQS_SECRET_ACCESS_KEY, safe="")
    ),
)
AWS_SQS_MAX_RECEIVE_COUNT = env.int("AWS_SQS_MAX_RECEIVE_COUNT", default=5)

AWS_SQS_MAX_YIELD_COUNT = env.int("AWS_SQS_MAX_YIELD_COUNT", default=25)
AWS_SQS_MAX_HOUNDI_YIELD_COUNT = env.int("AWS_SQS_MAX_HOUNDI_YIELD_COUNT", default=10)
AWS_NAME_PREFIX = env("AWS_NAME_PREFIX", default=env("USER", default="anonymous") + "-")

HOUNDIGRADE_RESULTS_QUEUE_NAME = env(
    "HOUNDIGRADE_RESULTS_QUEUE_NAME", default=AWS_NAME_PREFIX + "inspection_results"
)

if env.bool("HOUNDIGRADE_ENABLE_SENTRY", default=False):
    HOUNDIGRADE_ENABLE_SENTRY = True
    HOUNDIGRADE_SENTRY_DSN = env("HOUNDIGRADE_SENTRY_DSN")
    HOUNDIGRADE_SENTRY_RELEASE = (
        HOUNDIGRADE_ECS_IMAGE_TAG
        if HOUNDIGRADE_ECS_IMAGE_TAG
        else env("HOUNDIGRADE_SENTRY_RELEASE")
    )
    HOUNDIGRADE_SENTRY_ENVIRONMENT = env("HOUNDIGRADE_SENTRY_ENVIRONMENT")
else:
    HOUNDIGRADE_ENABLE_SENTRY = False

AWS_CLOUDTRAIL_EVENT_URL = env(
    "AWS_CLOUDTRAIL_EVENT_URL",
    default="https://sqs.us-east-1.amazonaws.com/123456789/cloudigrade-s3",
)

AWS_S3_BUCKET_NAME = env(
    "AWS_S3_BUCKET_NAME", default="{0}cloudigrade".format(AWS_NAME_PREFIX)
)
AWS_S3_BUCKET_LC_NAME = env("AWS_S3_BUCKET_LC_NAME", default="s3_lifecycle_policy")
AWS_S3_BUCKET_LC_IA_TRANSITION = env.int("AWS_S3_BUCKET_LC_IA_TRANSITION", default=30)
AWS_S3_BUCKET_LC_GLACIER_TRANSITION = env.int(
    "AWS_S3_BUCKET_LC_GLACIER_TRANSITION", default=60
)
AWS_S3_BUCKET_LC_MAX_AGE = env.int("AWS_S3_BUCKET_LC_MAX_AGE", default=1460)

CLOUDTRAIL_NAME_PREFIX = "cloudigrade-"

CELERY_BROKER_TRANSPORT_OPTIONS = {
    "queue_name_prefix": AWS_NAME_PREFIX,
    "region": AWS_SQS_REGION,
}
CELERY_BROKER_URL = AWS_SQS_URL
QUEUE_EXCHANGE_NAME = None

SCHEDULE_VERIFY_VERIFY_TASKS_INTERVAL = env.int(
    "SCHEDULE_VERIFY_VERIFY_TASKS_INTERVAL", default=60 * 60 * 24
)  # 24 Hours)

MAX_ALLOWED_INSPECTION_ATTEMPTS = env.int("MAX_ALLOWED_INSPECTION_ATTEMPTS", default=5)

INSPECT_PENDING_IMAGES_MIN_AGE = env.int(
    "INSPECT_PENDING_IMAGES_MIN_AGE", default=60 * 60 * 12  # 12 hours
)

DELETE_INACTIVE_USERS_MIN_AGE = env.int(
    "DELETE_INACTIVE_USERS_MIN_AGE", default=60 * 60 * 24
)

CELERY_TASK_ROUTES = {
    # api.tasks
    "api.tasks.create_from_sources_kafka_message": {
        "queue": "create_from_sources_kafka_message"
    },
    "api.tasks.delete_cloud_account": {"queue": "delete_cloud_account"},
    "api.tasks.delete_from_sources_kafka_message": {
        "queue": "delete_from_sources_kafka_message"
    },
    "api.tasks.delete_inactive_users": {"queue": "delete_inactive_users"},
    "api.tasks.inspect_pending_images": {"queue": "inspect_pending_images"},
    "api.tasks.persist_inspection_cluster_results_task": {
        "queue": "persist_inspection_cluster_results_task"
    },
    "api.tasks.process_instance_event": {"queue": "process_instance_event"},
    # api.clouds.aws.tasks
    "api.clouds.aws.tasks.repopulate_ec2_instance_mapping": {
        "queue": "repopulate_ec2_instance_mapping"
    },
    "api.clouds.aws.tasks.configure_customer_aws_and_create_cloud_account": {
        "queue": "configure_customer_aws_and_create_cloud_account"
    },
    "api.clouds.aws.tasks.initial_aws_describe_instances": {
        "queue": "initial_aws_describe_instances"
    },
    "api.clouds.aws.tasks.copy_ami_snapshot": {"queue": "copy_ami_snapshot"},
    "api.clouds.aws.tasks.copy_ami_to_customer_account": {
        "queue": "copy_ami_to_customer_account"
    },
    "api.clouds.aws.tasks.remove_snapshot_ownership": {
        "queue": "remove_snapshot_ownership"
    },
    "api.clouds.aws.tasks.create_volume": {"queue": "create_volume"},
    "api.clouds.aws.tasks.enqueue_ready_volume": {"queue": "enqueue_ready_volumes"},
    "api.clouds.aws.tasks.delete_snapshot": {"queue": "delete_snapshot"},
    "api.clouds.aws.tasks.scale_up_inspection_cluster": {
        "queue": "scale_up_inspection_cluster"
    },
    "api.clouds.aws.tasks.attach_volumes_to_cluster": {
        "queue": "attach_volumes_to_cluster"
    },
    "api.clouds.aws.tasks.run_inspection_cluster": {"queue": "run_inspection_cluster"},
    "api.clouds.aws.tasks.scale_down_cluster": {"queue": "scale_down_cluster"},
    "api.clouds.aws.tasks.analyze_log": {"queue": "analyze_log"},
    "api.tasks.calculate_max_concurrent_usage": {
        "queue": "calculate_max_concurrent_usage"
    },
    "api.tasks.enable_account": {"queue": "enable_account"},
    "api.tasks.notify_application_availability_task": {
        "queue": "notify_application_availability_task"
    },
}

# Limit in seconds for how long we expect the inspection cluster instance to exist.
INSPECTION_CLUSTER_INSTANCE_AGE_LIMIT = env.int(
    "INSPECTION_CLUSTER_INSTANCE_AGE_LIMIT", default=10 * 60  # 10 minutes
)

# Delay in seconds for concurrent usage calculation
SCHEDULE_CONCURRENT_USAGE_CALCULATION_DELAY = env.int(
    "SCHEDULE_CONCURRENT_USAGE_CALCULATION_DELAY", default=30 * 60
)

# Misc Config Values
CLOUDIGRADE_VERSION = env("IMAGE_TAG", default=env("CLOUDIGRADE_VERSION", default=None))
CLOUDIGRADE_ENVIRONMENT = env("CLOUDIGRADE_ENVIRONMENT", default=None)
VERBOSE_INSIGHTS_IDENTITY_HEADER_LOGGING = env.bool(
    "VERBOSE_INSIGHTS_IDENTITY_HEADER_LOGGING", default=False
)
VERBOSE_SOURCES_NOTIFICATION_LOGGING = env.bool(
    "VERBOSE_SOURCES_NOTIFICATION_LOGGING", default=False
)

# Various HEADER names
CLOUDIGRADE_REQUEST_HEADER = "X-CLOUDIGRADE-REQUEST-ID"
INSIGHTS_REQUEST_ID_HEADER = "HTTP_X_RH_INSIGHTS_REQUEST_ID"
INSIGHTS_IDENTITY_HEADER = "HTTP_X_RH_IDENTITY"
INSIGHTS_IDENTITY_ACCOUNT_HEADER = "HTTP_X_RH_IDENTITY_ACCOUNT"
INSIGHTS_IDENTITY_ORG_ADMIN_HEADER = "HTTP_X_RH_IDENTITY_ORG_ADMIN"

# Sources/Kafka Listener Values
LISTENER_TOPIC = env("LISTENER_TOPIC", default="platform.sources.event-stream")
LISTENER_GROUP_ID = env("LISTENER_GROUP_ID", default="cloudmeter_ci")
LISTENER_SERVER = env(
    "LISTENER_SERVER", default="platform-mq-ci-kafka-bootstrap.platform-mq-ci.svc"
)
LISTENER_PORT = env.int("LISTENER_PORT", default=9092)
LISTENER_METRICS_PORT = env.int("LISTENER_METRICS_PORT", default=8080)

SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA = env.bool(
    "SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA",
    default=True,
)

SOURCES_API_BASE_URL = env(
    "SOURCES_API_BASE_URL",
    default="http://sources-api.sources-ci.svc:8080",
)

SOURCE_API_INTERNAL_URI = "/internal/v1.0/"
SOURCES_API_EXTERNAL_URI = "/api/sources/v3.0/"

SOURCES_CLOUDMETER_ARN_AUTHTYPE = "cloud-meter-arn"
SOURCES_CLOUDMETER_AUTHTYPES = (SOURCES_CLOUDMETER_ARN_AUTHTYPE,)
SOURCES_RESOURCE_TYPE = "Application"

# Sources Availability Check Values
SOURCES_STATUS_TOPIC = env("SOURCES_STATUS_TOPIC", default="platform.sources.status")
SOURCES_AVAILABILITY_EVENT_TYPE = env(
    "SOURCES_AVAILABILITY_EVENT_TYPE",
    default="availability_status",
)

# Cache ttl settings
CACHE_TTL_DEFAULT = env.int("CACHE_TTL_DEFAULT", default=60)

CACHE_TTL_SOURCES_APPLICATION_TYPE_ID = env.int(
    "CACHE_TTL_SOURCES_APPLICATION_TYPE_ID", default=CACHE_TTL_DEFAULT
)
