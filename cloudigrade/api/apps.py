import logging

from django.apps import AppConfig
from django.conf import settings


logger = logging.getLogger(__name__)

# A list of application settings that we want logged on app startup
APPLICATION_SETTINGS_TO_LOG = [
    "CLOUDIGRADE_ENVIRONMENT",
    "CLOUDIGRADE_VERSION",
    "DEBUG",
    "INSPECTION_CLUSTER_INSTANCE_AGE_LIMIT",
    "INSPECT_PENDING_IMAGES_MIN_AGE",
    "IS_PRODUCTION",
    "MAX_ALLOWED_INSPECTION_ATTEMPTS",
    "SCHEDULE_CONCURRENT_USAGE_CALCULATION_DELAY",
    "SCHEDULE_VERIFY_VERIFY_TASKS_INTERVAL",
    "VERBOSE_INSIGHTS_IDENTITY_HEADER_LOGGING",
    "VERBOSE_SOURCES_NOTIFICATION_LOGGING",
]

# A list of houndigrade settings that we want logged on app startup
HOUNDIGRADE_SETTINGS_TO_LOG = [
    "HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME",
    "HOUNDIGRADE_AWS_AVAILABILITY_ZONE",
    "HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE",
    "HOUNDIGRADE_ECS_CLUSTER_NAME",
    "HOUNDIGRADE_ECS_FAMILY_NAME",
    "HOUNDIGRADE_ECS_IMAGE_NAME",
    "HOUNDIGRADE_ECS_IMAGE_TAG",
    "HOUNDIGRADE_ENABLE_SENTRY",
    "HOUNDIGRADE_EXCHANGE_NAME",
    "HOUNDIGRADE_RESULTS_QUEUE_NAME",
]

# A list of AWS settings that we want logged on app startup
AWS_SETTINGS_TO_LOG = [
    "AWS_CLOUDTRAIL_EVENT_URL",
    "AWS_NAME_PREFIX",
    "AWS_S3_BUCKET_LC_GLACIER_TRANSITION",
    "AWS_S3_BUCKET_LC_IA_TRANSITION",
    "AWS_S3_BUCKET_LC_MAX_AGE",
    "AWS_S3_BUCKET_LC_NAME",
    "AWS_S3_BUCKET_NAME",
    "AWS_SQS_MAX_HOUNDI_YIELD_COUNT",
    "AWS_SQS_MAX_RECEIVE_COUNT",
    "AWS_SQS_MAX_YIELD_COUNT",
    "AWS_SQS_REGION",
    "S3_DEFAULT_REGION",
    "SQS_DEFAULT_REGION",
]

# A list of Kafka settings that we want logged on app startup
KAFKA_SETTINGS_TO_LOG = [
    "KAFKA_SESSION_TIMEOUT_MS",
    "LISTENER_AUTO_COMMIT",
    "LISTENER_GROUP_ID",
    "LISTENER_PORT",
    "LISTENER_SERVER",
    "LISTENER_TIMEOUT",
    "LISTENER_TOPIC",
    "SOURCES_API_BASE_URL",
    "SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA",
    "SOURCES_STATUS_TOPIC",
]


class ApiConfig(AppConfig):
    name = "api"

    def ready(self):
        self.log_env_settings()

    def log_env_settings(self):
        """Log a subset of non secret environment settings."""
        logger.info("Application Settings:")
        for setting in APPLICATION_SETTINGS_TO_LOG:
            logger.info(f"{setting}: {getattr(settings, setting, None)}")

        logger.info("Houndigrade Settings:")
        for setting in HOUNDIGRADE_SETTINGS_TO_LOG:
            logger.info(f"{setting}: {getattr(settings, setting, None)}")

        logger.info("AWS Settings:")
        for setting in AWS_SETTINGS_TO_LOG:
            logger.info(f"{setting}: {getattr(settings, setting, None)}")

        logger.info("Kafka/Sources Settings:")
        for setting in KAFKA_SETTINGS_TO_LOG:
            logger.info(f"{setting}: {getattr(settings, setting, None)}")
