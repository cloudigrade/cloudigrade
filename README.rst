***********
cloudigrade
***********

|license| |Build Status| |codecov|


What is cloudigrade?
====================

**cloudigrade** is an open-source suite of tools for tracking RHEL use in public cloud platforms. **cloudigrade** actively checks a user's account in a particular cloud for running instances, tracks when instances are powered on, determines if RHEL is installed on them, and provides the ability to generate reports to see how many cloud compute resources have been used in a given time period.


What are "Doppler" and "Cloud Meter"?
-------------------------------------

Doppler was an early code name for **cloudigrade**. Cloud Meter is a product-ized Red Hat name for its running **cloudigrade** service. ``cloudigrade == Doppler == Cloud Meter`` for all intents and purposes. 😉


Running cloudigrade
===================

Developer Environment
---------------------

Because **cloudigrade** is actually a suite of interacting services, setting up a development environment may require installing some or all of the following dependencies:

-  Python 3.8
-  `poetry <https://python-poetry.org/docs/>`_
-  `tox <https://tox.readthedocs.io/>`_
-  `Docker Desktop <https://docs.docker.com/get-docker/>`_
-  `gettext <https://www.gnu.org/software/gettext/>`_
-  `PostgreSQL <https://www.postgresql.org/download/>`_
-  `AWS Command Line Interface <https://aws.amazon.com/cli/>`_
-  `Azure Command-Line Interface <https://docs.microsoft.com/en-us/cli/azure/>`_


macOS dependencies
~~~~~~~~~~~~~~~~~~

The following commands should install everything you need:

.. code-block:: bash

    brew update
    brew install python@3.8 gettext awscli azure-cli postgresql openssl curl librdkafka tox poetry


Linux dependencies
~~~~~~~~~~~~~~~~~~

We recommend developing on the latest version of Fedora. Follow the following commands to install the dependencies:

.. code-block:: bash

    sudo dnf install awscli gettext postgresql-devel librdkafka-devel -y


Python 3.8.x
~~~~~~~~~~~~

This step is optional, but we recommend you install a local Python version via `pyenv <https://github.com/pyenv/pyenv#installation>`_ instead of using the brew or dnf version. This will ensure you keep a *specific* stable version when you are working on **cloudigrade**. For example:

.. code-block:: bash

    pyenv install 3.8.7
    pyenv local


Virtual Environment (via Poetry)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

All Python developers should use a virtual environments to isolate their package dependencies. **cloudigrade** developers use `poetry <https://python-poetry.org/docs/>`_ and maintain its ``pyproject.toml`` and ``poetry.lock`` files with appropriate up-to-date requirements.

Once you have poetry installed, use it to install our Python package requirements:

.. code-block:: sh

    poetry env remove
    poetry install

If you plan to run **cloudigrade** or Celery locally on macOS, the required ``pycurl`` package may fail to install or may install improperly despite ``poetry install`` appearing to complete successfully. You should verify that ``pycurl`` is installed correctly by simply importing it in a Python shell like this:

.. code-block:: sh

    poetry run python -c 'import pycurl'

If you see no output, everything is okay! Otherwise (e.g. "libcurl link-time ssl backend (openssl) is different from compile-time ssl backend (none/other)"), it may not have installed correctly. Try the following commands (macOS users only) to force reinstalling with the openssl backend:

.. code-block:: sh

    brew update
    brew install openssl curl-openssl
    brew doctor  # ...and resolve any known problems.

    poetry run pip uninstall pycurl -y

    BREW_PATH=$(brew --prefix)
    export LDFLAGS="-L${BREW_PATH}/opt/curl/lib -L${BREW_PATH}/opt/openssl/lib"
    export CPPFLAGS="-I${BREW_PATH}/opt/curl/include -I${BREW_PATH}/opt/openssl/include"
    export PYCURL_SSL_LIBRARY="openssl"

    poetry install
    poetry run python -c 'import pycurl'

If this resolves the import error, you may also need to export all of those variables any time you have `tox` recreate its own virtual environments.

If using a system that has dnf, try the following commands:

.. code-block:: sh

    poetry run pip uninstall pycurl -y
    sudo dnf install openssl libcurl-devel
    export PYCURL_SSL_LIBRARY=openssl
    poetry install

Try the aforementioned import commands again, and all should be good. If not, kindly reach out to another **cloudigrade** developer to seek assistance!

After finishing the installation of dependencies, you can instantiate a shell uses the virtual environment by running ``poetry shell``.


macOS Big Sur Troubleshooting
*****************************

If you're working with macOS Big Sur you may run into issues around the system version number, in which case set ``SYSTEM_VERSION_COMPAT=1`` which will make macOS report back ``10.16`` instead of ``11.X``. For example,

.. code-block:: sh

    SYSTEM_VERSION_COMPAT=1 poetry install

You'll likely also run into more issues with installing pycurl. Follow the following steps to get back on track.

.. code-block:: sh

    poetry shell
    pip uninstall pycurl -y
    export LDFLAGS="-L${BREW_PATH}/opt/curl/lib"
    export CPPFLAGS="-I${BREW_PATH}/opt/curl/include"
    pip install --no-cache-dir --compile --ignore-installed --install-option="--with-openssl" --install-option="--openssl-dir=/usr/local/opt/openssl@1.1" pycurl


Configure AWS account for cloudigrade
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you haven't already, create an `Amazon Web Services <https://aws.amazon.com/>`_ account for **cloudigrade** to use for its AWS API calls. You will need the AWS Access Key ID, AWS Secret Access Key, and region name where the account operates.

**IMPORTANT NOTE**: This should *not* be the same AWS account that you use to simulate customer activity for tracking and inspection. **cloudigrade** *itself* requires a dedicated AWS account to perform various actions. We also strongly recommend creating a new AWS IAM user with its own credentials for use here instead of using your personal AWS account credentials.

Use the AWS CLI to save that configuration to your local system:

.. code-block:: bash

    aws configure

You can verify that settings were stored correctly by checking the files at ``~/.aws/{config,credentials}``. We *strongly* recommend using separate profiles for **cloudigrade** and any other personal or testing AWS accounts.

**cloudigrade** requires several entities to exist in its AWS account to track data and perform inspection of images that originated from other customer AWS accounts. Use commands like the following to run our included Ansible playbook to ensure the required AWS entities exist in **cloudigrade**'s AWS account:

.. code-block:: sh

    # start from the top level of the project repo
    cd ~/projects/cloudigrade

    # clear any existing AWS credentials to ensure you use the correct ones
    unset AWS_PROFILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY

    # set the AWS_PROFILE you defined earlier for cloudigrade,
    # or set the AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY directly
    export AWS_PROFILE="my-aws-cloudigrade-profile"

    # used to template various AWS entity names
    export CLOUDIGRADE_ENVIRONMENT="${USER}"

    # required in some macOS versions. YMMV.
    export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

    # run the playbook to configure everything!
    ANSIBLE_CONFIG=./deployment/playbooks/ansible.cfg poetry run ansible-playbook \
        -e env=${CLOUDIGRADE_ENVIRONMENT}\
        deployment/playbooks/manage-cloudigrade.yml

Running the Ansible playbook should be an idempotent operation. It should always try to put the entities in the AWS account in the same desired state, and it should be safe to run repeatedly.

If you want to undo that operation and effectively *remove* everything the playbook created and configured for you, set the same environment variables but add the ``-e aws_state=absent`` argument to the ``ansible-playbook`` command like the following:

.. code-block:: sh

    ANSIBLE_CONFIG=./deployment/playbooks/ansible.cfg poetry run ansible-playbook \
        -e env=${CLOUDIGRADE_ENVIRONMENT} \
        -e aws_state=absent \
        deployment/playbooks/manage-cloudigrade.yml


Configure local environment for cloudigrade
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Define environment variables
****************************

TL;DR: to get started, set at least the following environment variables before trying to run **cloudigrade** locally:

- ``DJANGO_SETTINGS_MODULE=config.settings.local``
- ``CLOUDIGRADE_ENVIRONMENT="${USER}"``
- ``AWS_ACCESS_KEY_ID="your cloudigrade aws access key id"``
- ``AWS_SECRET_ACCESS_KEY="your cloudigrade aws secret access key"``

If you do not set ``DJANGO_SETTINGS_MODULE``, you may need to include the ``--settings=config.settings.local`` argument with any Django admin or management commands you run.

**cloudigrade** derives several other important configs using the value of ``CLOUDIGRADE_ENVIRONMENT``. In deployed stage and production environments, for example, this variable may have the values "stage" and "prod" respectively. You should define ``CLOUDIGRADE_ENVIRONMENT`` with a value that is *reasonably unique to your own development environment*. We recommend setting it with your username like ``${USER}`` to minimize potential collisions with other nearby developers.

Credentials for **cloudigrade**'s AWS account must be set in your local environment using ``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY``. Even if you don't intend to work with AWS at first, these must not be empty or else app startup will fail. If you need to start the app without interacting with AWS, you may set dummy values in these variables for partial functionality.

The local config assumes you are running PostgreSQL on ``localhost:5432`` with the default ``postgres`` database and ``postgres`` user with no password set. You may want to change those default values with:

- ``DJANGO_DATABASE_HOST``
- ``DJANGO_DATABASE_PORT``
- ``DJANGO_DATABASE_NAME``
- ``DJANGO_DATABASE_USER``
- ``DJANGO_DATABASE_PASSWORD``

Many other optional variables are read at startup that may be useful for configuring your local environment, but most of the interesting ones should have reasonable defaults or be derived automatically from ``CLOUDIGRADE_ENVIRONMENT``. See ``cloudigrade/config/settings/*.py`` for more details.

Optional .env file
******************

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


Common commands
===============

Testing
-------

To run all local tests as well as our code-quality checking commands:

.. code-block:: sh

    tox

If ``tox`` cannot create its environment due to errors installing pycurl, try setting these environment variables first:

.. code-block:: sh

    export LDFLAGS=-L/usr/local/opt/openssl/lib
    export CPPFLAGS=-I/usr/local/opt/openssl/include
    export PYCURL_SSL_LIBRARY=openssl

If you wish to run *only* the tests:

.. code-block:: sh

    make unittest

If you wish to run a higher-level suite of integration tests, see `integrade <https://github.com/cloudigrade/integrade>`_.

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
For a local deployment, this means including a ``HTTP_X_RH_IDENTITY``
header in all requests.

API access is restricted to authenticated users.

For more information about this header see `examples. <./docs/rest-api-example.rst#Authorization>`_


When accessing any endpoint with the ``HTTP_X_RH_IDENTITY`` header,
if the user found in the header does not exist, it will be created.
It is also possible to programmatically create users on the command line,
for instance for testing. To create a user this way, use:

.. code-block:: sh

    make user


Message Broker
==============

Amazon SQS is used to broker messages between **cloudigrade**, Celery workers, and houndigrade.


Kafka Listener
==============

``listen_to_sources`` is a special Django management command whose purpose is to listen to the Red Hat Insights platform Kafka instance. Currently we only listen to a topic from the `Sources API <https://github.com/RedHatInsights/sources-api>`_ to inform us of when new source authentication objects are created so we can proceed to add them to **cloudigrade**.

Several environment variables may override defaults from ``config.settings`` to configure this command:

- ``LISTENER_TOPIC`` - The topic to listen to
- ``LISTENER_GROUP_ID`` - The listener group
- ``LISTENER_SERVER`` - Kafka server
- ``LISTENER_PORT`` -  Kafka server port
- ``LISTENER_AUTO_COMMIT`` - Whether the messages being received should be marked as so
- ``LISTENER_TIMEOUT`` - Timeout of the listener
- ``LISTENER_PID_PATH`` - The path of the pid file
- ``SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA`` - bool to feature-flag creation and deletion of users and cloud accounts driven by Kafka messages. When disabled, cloudigrade will only log a message when it reads from the Kafka topic.

The listener will be automatically deployed to all OSD environments, including review. If you'd like to run it locally you don't need to do anything special, simply be in your virtual environment, set your environment variables, and call ``python cloudigrade/manage.py listen_to_sources``.

.. |license| image:: https://img.shields.io/github/license/cloudigrade/cloudigrade.svg
   :target: https://github.com/cloudigrade/cloudigrade/blob/master/LICENSE
.. |Build Status| image:: https://travis-ci.org/cloudigrade/cloudigrade.svg?branch=master
   :target: https://travis-ci.org/cloudigrade/cloudigrade
.. |codecov| image:: https://codecov.io/gh/cloudigrade/cloudigrade/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/cloudigrade/cloudigrade
