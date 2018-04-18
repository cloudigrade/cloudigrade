"""Base settings file."""
import environ
from psycopg2cffi import compat

compat.register()

ROOT_DIR = environ.Path(__file__) - 3
APPS_DIR = ROOT_DIR.path('cloudigrade')

env = environ.Env()

# .env file, should load only in development environment
READ_DOT_ENV_FILE = env.bool('DJANGO_READ_DOT_ENV_FILE', default=False)

if READ_DOT_ENV_FILE:
    # Operating System Environment variables have precedence over variables defined in the .env file,
    # that is to say variables from the .env files will only be used if not defined
    # as environment variables.
    env_file = str(ROOT_DIR.path('.env'))
    print('Loading : {}'.format(env_file))
    env.read_env(env_file)
    print('The .env file has been loaded. See base.py for more information')

# Important Security Settings
SECRET_KEY = env('DJANGO_SECRET_KEY', default='base')
DEBUG = env.bool('DJANGO_DEBUG', default=False)
ALLOWED_HOSTS = env('DJANGO_ALLOWED_HOSTS', default=['*'])

# AWS Defaults
S3_DEFAULT_REGION = env('S3_DEFAULT_REGION', default='us-east-1')
SQS_DEFAULT_REGION = env('SQS_DEFAULT_REGION', default='us-east-1')
HOUNDIGRADE_AWS_AVAILABILITY_ZONE = env('HOUNDIGRADE_AWS_AVAILABILITY_ZONE',
                                        default='us-east-1a')

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
    'rest_framework',
    'rest_framework.authtoken',
]

# Apps specific to this project go here
LOCAL_APPS = [
    'util.apps.UtilConfig',
    'account.apps.AccountConfig',
    'analyzer.apps.AnalyzerConfig',
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


# Django Rest Framework
# http://www.django-rest-framework.org/api-guide/settings/

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.TokenAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    )
}

# Message and Task Queues

RABBITMQ_USER = env('RABBITMQ_USER', default='guest')
RABBITMQ_PASSWORD = env('RABBITMQ_PASSWORD', default='guest')
RABBITMQ_HOST = env('RABBITMQ_HOST', default='localhost')
RABBITMQ_PORT = env('RABBITMQ_PORT', default='5672')
RABBITMQ_VHOST = env('RABBITMQ_VHOST', default='/')

RABBITMQ_URL = env(
    'RABBITMQ_URL',
    default='amqp://{}:{}@{}:{}/{}'.format(
        RABBITMQ_USER,
        RABBITMQ_PASSWORD,
        RABBITMQ_HOST,
        RABBITMQ_PORT,
        RABBITMQ_VHOST
    )
)
RABBITMQ_EXCHANGE_NAME = env('RABBITMQ_EXCHANGE_NAME', default='cloudigrade_inspectigrade')
RABBITMQ_QUEUE_NAME = env('RABBITMQ_QUEUE_NAME', default='machine_images')

# Celery specific duplicate of RABBITMQ_URL

CELERY_BROKER_URL = RABBITMQ_URL
CELERY_TASK_ROUTES = {
    'account.tasks.copy_ami_snapshot': {'queue': 'copy_ami_snapshot'},
    'account.tasks.create_volume': {'queue': 'create_volume'},
    'account.tasks.enqueue_ready_volume': {'queue': 'enqueue_ready_volumes'},
}
