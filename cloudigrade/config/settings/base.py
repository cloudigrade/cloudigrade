"""Base settings file."""
from urllib.parse import quote

import environ
import logging.config

ROOT_DIR = environ.Path(__file__) - 3
APPS_DIR = ROOT_DIR.path('cloudigrade')

env = environ.Env()

# .env file, should load only in development environment
READ_DOT_ENV_FILE = env.bool('DJANGO_READ_DOT_ENV_FILE', default=False)

if READ_DOT_ENV_FILE:
    # Operating System Environment variables have precedence over variables
    # defined in the .env file, that is to say variables from the .env files
    # will only be used if not defined as environment variables.
    env_file = str(ROOT_DIR.path('.env'))
    print('Loading : {}'.format(env_file))
    env.read_env(env_file)
    print('The .env file has been loaded. See base.py for more information')

# Important Security Settings
SECRET_KEY = env('DJANGO_SECRET_KEY', default='base')
DEBUG = env.bool('DJANGO_DEBUG', default=False)
ALLOWED_HOSTS = env('DJANGO_ALLOWED_HOSTS', default=['*'])

# Logging
# https://docs.djangoproject.com/en/dev/topics/logging/
# https://docs.python.org/3.6/library/logging.html
# https://www.caktusgroup.com/blog/2015/01/27/Django-Logging-Configuration-logging_config-default-settings-logger/
LOGGING_CONFIG = None
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s | %(levelname)s | '
                      '%(filename)s:%(funcName)s:%(lineno)d | %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': env('DJANGO_CONSOLE_LOG_LEVEL', default='INFO'),
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console',],
            'level': env('DJANGO_LOG_LEVEL', default='INFO'),
        },
        'django': {
            'propagate': True
        },
    },
}

logging.config.dictConfig(LOGGING)

CELERY_WORKER_LOG_FORMAT = ('%(asctime)s | %(levelname)s | %(filename)s:'
                            '%(funcName)s:%(lineno)d | %(message)s')

# AWS Defaults
S3_DEFAULT_REGION = env('S3_DEFAULT_REGION', default='us-east-1')
SQS_DEFAULT_REGION = env('SQS_DEFAULT_REGION', default='us-east-1')
HOUNDIGRADE_AWS_AVAILABILITY_ZONE = env('HOUNDIGRADE_AWS_AVAILABILITY_ZONE',
                                        default='us-east-1b')
HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME = env(
    'HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME',
    default='EC2ContainerService-inspectigrade-test-bws-us-east-1b-'
            'EcsInstanceAsg-JG9NX9WHX6NU'
)
HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE = env.int(
    'HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE',
    default=32
)
HOUNDIGRADE_ECS_CLUSTER_NAME = env(
    'HOUNDIGRADE_ECS_CLUSTER_NAME',
    default='inspectigrade-test-bws-us-east-1b'
)
HOUNDIGRADE_ECS_FAMILY_NAME = env(
    'HOUNDIGRADE_ECS_FAMILY_NAME',
    default='Houndigrade'
)
HOUNDIGRADE_ECS_IMAGE_NAME = env(
    'HOUNDIGRADE_ECS_IMAGE_NAME',
    default='cloudigrade/houndigrade'
)
HOUNDIGRADE_ECS_IMAGE_TAG = env(
    'HOUNDIGRADE_ECS_IMAGE_TAG',
    default='latest'
)
HOUNDIGRADE_DEBUG = env.bool('HOUNDIGRADE_DEBUG', default=False)
HOUNDIGRADE_EXCHANGE_NAME = env('HOUNDIGRADE_EXCHANGE_NAME', default='')

# Default apps go here
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

# Any pip installed apps will go here
THIRD_PARTY_APPS = [
    'raven.contrib.django.raven_compat',
    'django_celery_beat',
    'rest_framework',
    'rest_framework.authtoken',
    'djoser',
    'health_check',
    'health_check.db',
]

# Apps specific to this project go here
LOCAL_APPS = [
    'util.apps.UtilConfig',
    'account.apps.AccountConfig',
    'analyzer.apps.AnalyzerConfig',
    'dj_auth.apps.DjAuthConfig',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# Middleware

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/2.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ATOMIC_REQUESTS': env('DJANGO_ATOMIC_REQUESTS', default=True),
        'ENGINE': env('DJANGO_DATABASE_ENGINE', default='django.db.backends.postgresql_psycopg2'),
        'NAME': env('DJANGO_DATABASE_NAME', default='postgres'),
        'HOST': env('DJANGO_DATABASE_HOST', default='localhost'),
        'USER': env('DJANGO_DATABASE_USER', default='postgres'),
        'PASSWORD': env('DJANGO_DATABASE_PASSWORD', default='postgres'),
        'PORT': env('DJANGO_DATABASE_PORT', default=5432),
        'CONN_MAX_AGE': env('DJANGO_DATABASE_CONN_MAX_AGE', default=0),
    }
}

# Password validation
# https://docs.djangoproject.com/en/2.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/

STATIC_URL = env('DJANGO_STATIC_URL', default='/static/')
STATIC_ROOT = env('DJANGO_STATIC_ROOT', default=str(ROOT_DIR.path('static')))


# Raven
# https://sentry.io/onboarding/cloudigrade/cloudigrade-api/configure/python-django

RAVEN_CONFIG = {}  # Configured in prod.py


# Django Rest Framework
# http://www.django-rest-framework.org/api-guide/settings/

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.TokenAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'dj_auth.permissions.IsAuthenticated',
    ),
    'EXCEPTION_HANDLER': 'util.exceptions.api_exception_handler',
}


# Message and Task Queues

# For convenience in development environments, find defaults gracefully here.
AWS_SQS_REGION = env('AWS_SQS_REGION',
                     default=env('AWS_DEFAULT_REGION',
                                 default='us-east-1'))

AWS_SQS_ACCESS_KEY_ID = env('AWS_SQS_ACCESS_KEY_ID',
                            default=env('AWS_ACCESS_KEY_ID',
                                        default=''))
AWS_SQS_SECRET_ACCESS_KEY = env('AWS_SQS_SECRET_ACCESS_KEY',
                                default=env('AWS_SECRET_ACCESS_KEY',
                                            default=''))

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
    'AWS_SQS_URL',
    default='sqs://{}:{}@'.format(quote(AWS_SQS_ACCESS_KEY_ID, safe=''),
                                  quote(AWS_SQS_SECRET_ACCESS_KEY, safe=''))
)
AWS_SQS_MAX_RECEIVE_COUNT = env('AWS_SQS_MAX_RECEIVE_COUNT', default=5)
AWS_NAME_PREFIX = env('AWS_NAME_PREFIX',
                      default=env('USER', default='anonymous') + '-')

HOUNDIGRADE_RESULTS_QUEUE_NAME = env('HOUNDIGRADE_RESULTS_QUEUE_NAME',
                                      default=AWS_NAME_PREFIX + \
                                              'inspection_results')

if env.bool('HOUNDIGRADE_ENABLE_SENTRY', default=False):
    HOUNDIGRADE_ENABLE_SENTRY = True
    HOUNDIGRADE_SENTRY_DSN = env('HOUNDIGRADE_SENTRY_DSN')
    HOUNDIGRADE_SENTRY_RELEASE = env('HOUNDIGRADE_SENTRY_RELEASE')
    HOUNDIGRADE_SENTRY_ENVIRONMENT = env('HOUNDIGRADE_SENTRY_ENVIRONMENT')
else:
    HOUNDIGRADE_ENABLE_SENTRY = False

CLOUDTRAIL_EVENT_URL = env(
    'CLOUDTRAIL_EVENT_URL',
    default='https://sqs.us-east-1.amazonaws.com/123456789/test-cloudigrade-s3'
)

S3_BUCKET_NAME = env('S3_BUCKET_NAME', default='{0}cloudigrade'.format(AWS_NAME_PREFIX))

CLOUDTRAIL_NAME_PREFIX = 'cloudigrade-'

CELERY_BROKER_TRANSPORT_OPTIONS = {
    'queue_name_prefix': AWS_NAME_PREFIX,
    'region': AWS_SQS_REGION,
}
CELERY_BROKER_URL = AWS_SQS_URL
QUEUE_EXCHANGE_NAME = None

CELERY_TASK_ROUTES = {
    'account.tasks.initial_aws_describe_instances':
        {'queue': 'initial_aws_describe_instances'},
    'account.tasks.copy_ami_snapshot':
        {'queue': 'copy_ami_snapshot'},
    'account.tasks.copy_ami_to_customer_account':
        {'queue': 'copy_ami_to_customer_account'},
    'account.tasks.remove_snapshot_ownership':
        {'queue': 'remove_snapshot_ownership'},
    'account.tasks.create_volume':
        {'queue': 'create_volume'},
    'account.tasks.enqueue_ready_volume':
        {'queue': 'enqueue_ready_volumes'},
    'account.tasks.delete_snapshot':
        {'queue': 'delete_snapshot'},
    'account.tasks.scale_up_inspection_cluster':
        {'queue': 'scale_up_inspection_cluster'},
    'account.tasks.run_inspection_cluster':
        {'queue': 'run_inspection_cluster'},
    'account.tasks.persist_inspection_cluster_results_task':
        {'queue': 'persist_inspection_cluster_results_task'},
    'account.tasks.scale_down_cluster':
        {'queue': 'scale_down_cluster'},
    'analyzer.tasks.analyze_log':
        {'queue': 'analyze_log'},
}
CELERY_BEAT_SCHEDULE = {
    'scale_up_inspection_cluster_every_60_min': {
        'task': 'account.tasks.scale_up_inspection_cluster',
        # seconds
        'schedule': env.int('SCALE_UP_INSPECTION_CLUSTER_SCHEDULE', default=60 * 60),
    },
    'persist_inspection_cluster_results': {
        'task': 'account.tasks.persist_inspection_cluster_results_task',
        # seconds
        'schedule': env.int('PERSIST_INSPECTION_CLUSTER_RESULTS_SCHEDULE', default=5 * 60),
    },
    'analyze_log_every_2_mins': {
        'task': 'analyzer.tasks.analyze_log',
        # seconds
        'schedule': env.int('ANALYZE_LOG_SCHEDULE', default=2 * 60),
    },
}
