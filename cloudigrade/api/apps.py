import logging
import os

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)

# A list of application settings that we want logged on app startup
APPLICATION_SETTINGS_TO_LOG = [
    "CACHE_TTL_DEFAULT",
    "CACHE_TTL_SOURCES_APPLICATION_TYPE_ID",
    "CLOUDIGRADE_ENVIRONMENT",
    "CLOUDIGRADE_VERSION",
    "DEBUG",
    "INSPECTION_CLUSTER_INSTANCE_AGE_LIMIT",
    "INSPECT_PENDING_IMAGES_MIN_AGE",
    "IS_PRODUCTION",
    "MAX_ALLOWED_INSPECTION_ATTEMPTS",
    "SOURCES_ENABLE_DATA_MANAGEMENT",
    "VERBOSE_INSIGHTS_IDENTITY_HEADER_LOGGING",
    "VERBOSE_SOURCES_NOTIFICATION_LOGGING",
    "ENABLE_SYNTHETIC_DATA_REQUEST_HTTP_API",
    "TENANT_TRANSLATOR_HOST",
    "TENANT_TRANSLATOR_PORT",
    "TENANT_TRANSLATOR_SCHEME",
]

# A list of houndigrade settings that we want logged on app startup
HOUNDIGRADE_SETTINGS_TO_LOG = [
    "HOUNDIGRADE_ECS_IMAGE_NAME",
    "HOUNDIGRADE_ECS_IMAGE_TAG",
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
    "AWS_DEFAULT_REGION",
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

# A list of Watchtower/CloudWatch settings that we want logged on app startup
WATCHTOWER_SETTINGS_TO_LOG = [
    "CLOUDIGRADE_ENABLE_CLOUDWATCH",
    "CLOUDIGRADE_CW_LEVEL",
    "CLOUDIGRADE_CW_LOG_GROUP",
    "CLOUDIGRADE_CW_STREAM_NAME",
    "CLOUDIGRADE_CW_RETENTION_DAYS",
    "WATCHTOWER_USE_QUEUES",
    "WATCHTOWER_SEND_INTERVAL",
    "WATCHTOWER_MAX_BATCH_COUNT",
]

CREDENTIALS_TO_LOG_REDACTED = [
    "AWS_ACCESS_KEY_ID",
    "AWS_PROFILE",
    "AWS_SECRET_ACCESS_KEY",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_SP_OBJECT_ID",
    "AZURE_SUBSCRIPTION_ID",
    "AZURE_TENANT_ID",
]


class ApiConfig(AppConfig):
    name = "api"

    def ready(self):
        self.log_env_settings()
        self.log_redacted_credentials()

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

        logger.info("Watchtower/CloudWatch Settings:")
        for setting in WATCHTOWER_SETTINGS_TO_LOG:
            logger.info(f"{setting}: {getattr(settings, setting, None)}")

        logger.info('LOGGING["handlers"]:')
        logger.info(settings.LOGGING["handlers"])

    def log_redacted_credentials(self):
        """
        Log redacted secrets for diagnosing possible configuration issues.

        We redact all but the last *two* characters of every secret that has a value.
        Because secrets should always be *significantly* longer, the potential risk
        this adds if production logs were leaked should be minimal.
        """
        logger.info("Redacted Credentials:")
        for setting in CREDENTIALS_TO_LOG_REDACTED:
            value = getattr(settings, setting, None)
            if not value:
                value = os.environ.get(setting, None)
            redacted = "*" * 18 + value[-2:] if value else None
            logger.info(f"{setting}: {redacted}")
