.. contents:: :depth: 2

Development Setup
=================

Running **cloudigrade** locally may require installing some or all of the following dependencies:

-  Python 3.9
-  `poetry <https://python-poetry.org/docs/>`_
-  `tox <https://tox.readthedocs.io/>`_
-  `Podman <https://podman.io/>`_
-  `gettext <https://www.gnu.org/software/gettext/>`_
-  `PostgreSQL <https://www.postgresql.org/download/>`_
-  `AWS Command Line Interface <https://aws.amazon.com/cli/>`_
-  `Azure Command-Line Interface <https://docs.microsoft.com/en-us/cli/azure/>`_


macOS dependencies
------------------

The following commands should install everything you need:

.. code-block:: bash

    brew update
    brew install python@3.9 gettext awscli azure-cli postgresql librdkafka tox poetry podman

You may also want to ``brew install openshift-cli``. Although the OpenShift CLI is not required for local development and operation, it is required for deploying cloudigrade to OpenShift, including the `Ephemeral Cluster Deployment <https://github.com/cloudigrade/cloudigrade/wiki/Ephemeral-Cluster-Deployment>`_.

To start the podman machine that will be running the commands run:

.. code-block:: bash

    podman machine init
    podman machine start

    # you can check the status by running
    podman info


New to podman? Fortunately if you're already familiar with docker, the following rule is true: ``alias docker=podman``


Linux dependencies
------------------

We recommend developing on the latest version of Fedora. Follow the following commands to install the dependencies:

.. code-block:: bash

    sudo dnf install awscli gettext postgresql-devel librdkafka-devel podman -y


Python 3.9.x
------------

This step is optional, but we recommend you install a local Python version via `pyenv <https://github.com/pyenv/pyenv#installation>`_ instead of using the brew or dnf version. This will ensure you keep a *specific* stable version when you are working on **cloudigrade**. For example:

.. code-block:: bash

    pyenv install 3.9.7
    pyenv local


Virtual Environment (via Poetry)
--------------------------------

All Python developers should use a virtual environments to isolate their package dependencies. **cloudigrade** developers use `poetry <https://python-poetry.org/docs/>`_ and maintain its ``pyproject.toml`` and ``poetry.lock`` files with appropriate up-to-date requirements.

Once you have poetry installed, use it to install our Python package requirements:

.. code-block:: sh

    poetry env remove
    poetry install

After finishing the installation of dependencies, you can instantiate a shell uses the virtual environment by running ``poetry shell``.

macOS ``librdkafka`` Troubleshooting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If ``poetry`` or ``tox`` fail to install ``confluent-kafka`` due to problems with ``librdkafka`` like the following:

.. code-block::

    /private/var/folders/71/5v1_8dbd03j_nfxbb8bkb1q00000gn/T/pip-req-build-xeit5a49/src/confluent_kafka/src/confluent_kafka.h:23:10: fatal error: 'librdkafka/rdkafka.h' file not found
    #include <librdkafka/rdkafka.h>
                ^~~~~~~~~~~~~~~~~~~~~~
    1 error generated.
    error: command '/usr/bin/clang' failed with exit code 1

Set and export the following environment variables with the current ``librdkafka`` paths, and try your command again:

.. code-block:: sh

    export C_INCLUDE_PATH="$(brew --prefix)/Cellar/librdkafka/*/include"
    export LIBRARY_PATH="$(brew --prefix)/Cellar/librdkafka/*/lib"

Note that you may need to replace ``*`` in those paths with your latest version if you have multiple versions of ``librdkafka`` installed (this is very unlikely).

macOS Big Sur Troubleshooting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you're working with macOS Big Sur you may run into issues around the system version number, in which case set ``SYSTEM_VERSION_COMPAT=1`` which will make macOS report back ``10.16`` instead of ``11.X``. For example,

.. code-block:: sh

    SYSTEM_VERSION_COMPAT=1 poetry install


AWS account setup
-----------------

If you haven't already, work with another team member to gain access to an `Amazon Web Services <https://aws.amazon.com/>`_ account for **cloudigrade** to use for its AWS API calls. You will need the AWS Access Key ID, AWS Secret Access Key, and region name where the account operates.

**IMPORTANT NOTE**: This should *not* be the same AWS account that you use to simulate customer activity for tracking and inspection. **cloudigrade** *itself* requires a dedicated AWS account to perform various actions. We also strongly recommend creating a new AWS IAM user with its own credentials for use here instead of using your personal AWS account credentials.

Use the AWS CLI to save that configuration to your local system:

.. code-block:: bash

    aws configure

You can verify that settings were stored correctly by checking the files at ``~/.aws/{config,credentials}``. We *strongly* recommend using separate profiles for **cloudigrade** and any other personal or testing AWS accounts.


Azure Account Setup
-------------------

Next you'll need an Azure account. You can sign up for one, or login `here <https://portal.azure.com/>`_. You will need to get the tenant id, client id, subscription id, and the client secret.

The tenant id is your Azure directory id, the subscription id is as it says. To get the client id and secret follow these steps:

#. Log into the `Azure Portal <https://portal.azure.com/>`_
#. Navigate to the Azure Active Directory Blade.
#. In the left column, under `Manage`, select `App Registrations`.
#. Select `New Registration`
#. Name your app e.g. `cloudigrade-dev-kb`
#. Click Register. You should now be taken to your new App Registration.
#. Note your `Application (client) ID` on the Overview page, this is your `Client ID`.
#. In the left column, under `Manage`, select `Certificates & secrets`.
#. Select `New client secret`
#. Add a helpful description and expiration date.
#. Click Add. Your `Client Secret` is under the `Value` column.
#. Navigate back to the Azure Active Directory Blade.
#. In the left column, under `Manage`, select `Enterprise applications`.
#. You'll see the application you registered earlier listed, note the `Object ID` here, this is the `Object ID` you'll need below.

After you've acquired those values, set the environment variables:

- ``AZURE_CLIENT_ID="your client id from above"``
- ``AZURE_CLIENT_SECRET="your client secret from above"``
- ``AZURE_SP_OBJECT_ID="your object id from above"``
- ``AZURE_SUBSCRIPTION_ID="your azure subscription id"``
- ``AZURE_TENANT_ID="your azure directory id"``

Finally, before your deployment is able to talk to Azure, you'll need to create a role with all the necessary permissions.

#. Log into the `Azure Portal <https://portal.azure.com/>`_
#. Navigate to the Azure Subscription that you'll be using.
#. In the left column, select `Access control (IAM)`.
#. Select `Add -> Custom Role`
#. Name the role, click `Next`.
#. Select the `JSON` tab.
#. Paste the following JSON block replacing the permissions array only:

    .. code-block:: json

            "permissions": [
                {
                    "actions": [
                        "Microsoft.Compute/skus/read"
                    ],
                    "notActions": [],
                    "dataActions": [],
                    "notDataActions": []
                }
            ]

#. Click `Review + create` -> `Create`.
#. Select `Add -> Add a Role Assignment`
#. Role -> Select your newly created Role
#. Select -> Type your app registration name here and hit enter.
#. Select your app that mysteriously appeared.
#. Click `Save`.

You should now be ready to use Azure with cloudigrade.

Environment variables
---------------------

TL;DR: to get started, set at least the following environment variables before trying to run **cloudigrade** locally:

- ``DJANGO_SETTINGS_MODULE=config.settings.local``
- ``CLOUDIGRADE_ENVIRONMENT="${USER}"``
- ``AWS_ACCESS_KEY_ID="your cloudigrade aws access key id"``
- ``AWS_SECRET_ACCESS_KEY="your cloudigrade aws secret access key"``
- ``AZURE_CLIENT_ID="your azure client id"``
- ``AZURE_CLIENT_SECRET="your azure client secret"``
- ``AZURE_SUBSCRIPTION_ID="your azure subscription id"``
- ``AZURE_TENANT_ID="your azure directory id"``

If you do not set ``DJANGO_SETTINGS_MODULE``, you may need to include the ``--settings=config.settings.local`` argument with any Django admin or management commands you run.

**cloudigrade** derives several other important configs using the value of ``CLOUDIGRADE_ENVIRONMENT``. In deployed stage and production environments, for example, this variable may have the values "stage" and "prod" respectively. You should define ``CLOUDIGRADE_ENVIRONMENT`` with a value that is *reasonably unique to your own development environment*. We recommend setting it with your username like ``${USER}`` to minimize potential collisions with other nearby developers.

Credentials for **cloudigrade**'s AWS account must be set in your local environment using ``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY``. Even if you don't intend to work with AWS at first, these must not be empty or else app startup will fail. If you need to start the app without interacting with AWS, you may set dummy values in these variables for partial functionality.

Similar caveat applies for **cloudigrade**'s Azure account, it must be set in your local environment using ``AZURE_CLIENT_ID``,  ``AZURE_CLIENT_SECRET``, ``AZURE_SUBSCRIPTION_ID``, and ``AZURE_TENANT_ID``. Even if you don't intend to work with Azure at first, these must not be empty or else app startup will fail. If you need to start the app without interacting with Azure, you may set dummy values in these variables for partial functionality.

The local config assumes you are running PostgreSQL on ``localhost:5432`` with the default ``postgres`` database and ``postgres`` user with no password set. You may want to change those default values with:

- ``DJANGO_DATABASE_HOST``
- ``DJANGO_DATABASE_PORT``
- ``DJANGO_DATABASE_NAME``
- ``DJANGO_DATABASE_USER``
- ``DJANGO_DATABASE_PASSWORD``

Many other optional variables are read at startup that may be useful for configuring your local environment, but most of the interesting ones should have reasonable defaults or be derived automatically from ``CLOUDIGRADE_ENVIRONMENT``. See ``cloudigrade/config/settings/*.py`` for more details.


Optional .env file
~~~~~~~~~~~~~~~~~~

If you would like to set fewer environment variables, you may put most of your local variables in an optional ``.env`` file that **cloudigrade** will attempt to read at startup. At a minimum, you may want to keep at least these two environment variables:

- ``DJANGO_SETTINGS_MODULE=config.settings.local``
- ``ENV_FILE_PATH=/path/to/your/env/file``

If not specified, the default value for ``ENV_FILE_PATH`` looks for a file at ``/mnt/secret_store/.env``. The file at that path should have contents like a typical ``.env`` file. For example:

.. code-block::

    CLOUDIGRADE_ENVIRONMENT="brasmith-local"
    DJANGO_DEBUG="True"
    DJANGO_SECRET_KEY="my great secret"
    DJANGO_DATABASE_NAME="cloudigrade"
    DJANGO_DATABASE_USER="cloudigrade"
    AWS_ACCESS_KEY_ID="my aws access key id"
    AWS_SECRET_ACCESS_KEY="my secret access key"
    SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA="False"

If a file is not readable at that path, its loading will be skipped at startup, and **cloudigrade** will rely on environment variables to be set.


Common developer commands
=========================

Testing
-------

To run all local tests as well as our code-quality checking commands:

.. code-block:: sh

    tox

If you wish to run *only* the tests:

.. code-block:: sh

    make unittest

Updating API Example Docs
-------------------------

You may run the following Make target to generate the API examples documentation:

.. code-block:: sh

    make docs-api-examples

This will create many use-case-specific records in the database, simulate API calls through cloudigrade, and generate an updated document with the API calls. You should review any changes made by this command before adding and committing them to source control.

Generate openapi.json Files
---------------------------

Generation of the ``openapi.json`` and ``openapi-internal.json`` files uses the same mechanism that dynamically serves the specifications via the API, and the static files' contents should always match what the API serves dynamically. If you've recently made changes to the API and need to update the static files, run the following command:

.. code-block:: sh

    make openapi

Otherwise, if you'd simply like to verify that the current static files match the API, you can run the following command:

.. code-block:: sh

    make openapi-test


Authentication
==============

Custom HTTP header authentication is used to authenticate users.
For a local deployment, this means including the ``X-RH-IDENTITY``
header in all requests.

API access is restricted to authenticated users.

For more information about this header see `examples. <./docs/rest-api-examples.rst#Authorization>`_

Users are automatically created as needed when new customer sources are
defined by interactions with sources-api via Kafka messages. If you want
to create a user locally without interacting with sources-api and Kafka,
you may use this internal cloudigrade API:

.. code-block:: sh

    http localhost:8000/internal/api/cloudigrade/v1/users/ \
        account_number=12345 org_id=67890 is_permanent=true

You may give that API whatever ``account_number`` and ``org_id`` values
are appropriate, but note that setting ``is_permanent`` means that this
user will not be deleted by cloudigrade's periodic cleanup tasks even
if the user has no related data. Following this example, after creating
this user, I could make other API requests using ``X-RH-IDENTITY``
defined like this:

.. code-block:: sh

    X_RH_IDENTITY=$(echo '{
        "identity": {
            "account_number": "12345", "org_id":"67890"
        }
    }' | base64)

    http localhost:8000/api/cloudigrade/v2/instances/ \
        X-RH-IDENTITY:"${X_RH_IDENTITY}"


Message Broker
==============

Amazon SQS is used to notify **cloudigrade** of new inspection results or logs to analyze.
Redis is used to broker messages between **cloudigrade** and celery workers.


Kafka Listener
==============

``listen_to_sources`` is a special Django management command whose purpose is to listen to the Red Hat Insights platform Kafka instance. Currently we only listen to a topic from the `Sources API <https://github.com/RedHatInsights/sources-api>`_ to inform us of when new source authentication objects are created so we can proceed to add them to **cloudigrade**.

Several environment variables may override defaults from ``config.settings`` to configure this command:

- ``KAFKA_SERVER_HOST`` - Kafka server host
- ``KAFKA_SERVER_PORT`` -  Kafka server port
- ``LISTENER_TOPIC`` - The topic to listen to
- ``LISTENER_GROUP_ID`` - The listener group
- ``LISTENER_AUTO_COMMIT`` - Whether the messages being received should be marked as so
- ``LISTENER_TIMEOUT`` - Timeout of the listener
- ``LISTENER_PID_PATH`` - The path of the pid file
- ``SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA`` - bool to feature-flag creation and deletion of users and cloud accounts driven by Kafka messages. When disabled, cloudigrade will only log a message when it reads from the Kafka topic.

The listener will be automatically deployed to all OSD environments, including ephemeral. If you'd like to run it locally you don't need to do anything special, simply be in your virtual environment, set your environment variables, and call ``python cloudigrade/manage.py listen_to_sources``.
