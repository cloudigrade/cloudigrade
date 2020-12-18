"""Base settings file."""
from decimal import Decimal
from urllib.parse import quote

import environ
import logging.config

from boto3.session import Session

ROOT_DIR = environ.Path(__file__) - 3
APPS_DIR = ROOT_DIR.path("cloudigrade")

env = environ.Env()

# .env file, should load only in development environment
READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)

if READ_DOT_ENV_FILE:
    # Operating System Environment variables have precedence over variables
    # defined in the .env file, that is to say variables from the .env files
    # will only be used if not defined as environment variables.
    env_file = str(ROOT_DIR.path(".env"))
    print("Loading : {}".format(env_file))
    env.read_env(env_file)
    print("The .env file has been loaded. See base.py for more information")

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

if env.bool("CLOUDIGRADE_ENABLE_CLOUDWATCH", default=False):
    print("Configuring CloudWatch...")
    cw_boto3_session = Session(
        aws_access_key_id=env("CW_AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=env("CW_AWS_SECRET_ACCESS_KEY"),
        region_name=env("CW_AWS_REGION_NAME"),
    )
    LOGGING["handlers"]["watchtower"] = {
        "level": env("CLOUDIGRADE_CW_LEVEL", default="INFO"),
        "class": "watchtower.CloudWatchLogHandler",
        "boto3_session": cw_boto3_session,
        "log_group": env("CLOUDIGRADE_CW_LOG_GROUP"),
        "stream_name": env("CLOUDIGRADE_CW_STREAM_NAME"),
        "formatter": "verbose",
        "use_queues": False,
    }
    for logger_name, logger in LOGGING["loggers"].items():
        print(f"Appending watchtower to handlers for '{logger_name}'")
        logger["handlers"].append("watchtower")
    print("Configured CloudWatch.")
    print(f"LOGGING with CloudWatch is {LOGGING}")

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
    "DEFAULT_AUTHENTICATION_CLASSES": ("api.authentication.ThreeScaleAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "EXCEPTION_HANDLER": "util.exceptions.api_exception_handler",
}

INSIGHTS_PAGINATION_APP_PATH = "/api/cloudigrade"

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

# We appear to be receiving ~300 messages an hour currently,
AWS_SQS_MAX_YIELD_COUNT = env.int("AWS_SQS_MAX_YIELD_COUNT", default=100)
AWS_SQS_MAX_HOUNDI_YIELD_COUNT = env.int("AWS_SQS_MAX_HOUNDI_YIELD_COUNT", default=10)
AWS_NAME_PREFIX = env("AWS_NAME_PREFIX", default=env("USER", default="anonymous") + "-")

HOUNDIGRADE_RESULTS_QUEUE_NAME = env(
    "HOUNDIGRADE_RESULTS_QUEUE_NAME", default=AWS_NAME_PREFIX + "inspection_results"
)

if env.bool("HOUNDIGRADE_ENABLE_SENTRY", default=False):
    HOUNDIGRADE_ENABLE_SENTRY = True
    HOUNDIGRADE_SENTRY_DSN = env("HOUNDIGRADE_SENTRY_DSN")
    HOUNDIGRADE_SENTRY_RELEASE = env("HOUNDIGRADE_SENTRY_RELEASE")
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
}
# Remember: the "schedule" values are integer numbers of seconds.
CELERY_BEAT_SCHEDULE = {
    # api.tasks
    "delete_inactive_users": {
        "task": "api.tasks.delete_inactive_users",
        "schedule": env.int("DELETE_INACTIVE_USERS_SCHEDULE", default=24 * 60 * 60),
    },
    "persist_inspection_cluster_results": {
        "task": "api.tasks.persist_inspection_cluster_results_task",
        "schedule": env.int(
            "HOUNDIGRADE_ECS_PERSIST_INSPECTION_RESULTS_SCHEDULE", default=5 * 60
        ),
    },
    "inspect_pending_images": {
        "task": "api.tasks.inspect_pending_images",
        "schedule": env.int("INSPECT_PENDING_IMAGES_SCHEDULE", default=15 * 60),
    },
    # api.clouds.aws.tasks
    "scale_up_inspection_cluster_every_60_min": {
        "task": "api.clouds.aws.tasks.scale_up_inspection_cluster",
        "schedule": env.int(
            "HOUNDIGRADE_ECS_SCALE_UP_CLUSTER_SCHEDULE", default=60 * 60
        ),
    },
    "analyze_log_every_2_mins": {
        "task": "api.clouds.aws.tasks.analyze_log",
        "schedule": env.int("ANALYZE_LOG_SCHEDULE", default=2 * 60),
    },
    "repopulate_ec2_instance_mapping_every_week": {
        "task": "api.clouds.aws.tasks.repopulate_ec2_instance_mapping",
        "schedule": env.int(
            "AWS_REPOPULATE_EC2_INSTANCE_MAPPING_SCHEDULE",
            default=60 * 60 * 24 * 7,  # 1 week in seconds
        ),
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
CLOUDIGRADE_VERSION = env("CLOUDIGRADE_VERSION", default=None)
CLOUDIGRADE_ENVIRONMENT = env("CLOUDIGRADE_ENVIRONMENT", default=None)

# Various HEADER names
CLOUDIGRADE_REQUEST_HEADER = "X-CLOUDIGRADE-REQUEST-ID"
INSIGHTS_REQUEST_ID_HEADER = "HTTP_X_RH_INSIGHTS_REQUEST_ID"
INSIGHTS_IDENTITY_HEADER = "HTTP_X_RH_IDENTITY"
VERBOSE_INSIGHTS_IDENTITY_HEADER_LOGGING = env.bool(
    "VERBOSE_INSIGHTS_IDENTITY_HEADER_LOGGING", default=False
)

# Sources/Kafka Listener Values
LISTENER_TOPIC = env("LISTENER_TOPIC", default="platform.sources.event-stream")
LISTENER_GROUP_ID = env("LISTENER_GROUP_ID", default="cloudmeter_ci")
LISTENER_SERVER = env(
    "LISTENER_SERVER", default="platform-mq-ci-kafka-bootstrap.platform-mq-ci.svc"
)
LISTENER_PORT = env.int("LISTENER_PORT", default=9092)
LISTENER_AUTO_COMMIT = env.bool("LISTENER_AUTO_COMMIT", default=True)
LISTENER_TIMEOUT = env.int("LISTENER_TIMEOUT", default=1000)
KAFKA_SESSION_TIMEOUT_MS = env.int("KAFKA_SESSION_TIMEOUT_MS", default=20000)

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

SOURCE_DESTROY_EVENT = "Source.destroy"
APPLICATION_AUTHENTICATION_DESTROY_EVENT = "ApplicationAuthentication.destroy"

KAFKA_DESTROY_EVENTS = (
    SOURCE_DESTROY_EVENT,
    APPLICATION_AUTHENTICATION_DESTROY_EVENT,
)
