***********
cloudigrade
***********

|license| |Build Status| |codecov| |Updates| |Python 3|


What is cloudigrade?
====================

**cloudigrade** is an open-source suite of tools for tracking Linux distribution use (although chiefly targeting RHEL) in public cloud platforms. **cloudigrade** actively checks a user's account in a particular cloud for running instances, tracks when instances are powered on, determines what Linux distributions are installed on them, and provides the ability to generate reports to see how many cloud compute resources have been used in a given time period.


What is this "Doppler" I see referenced in various places?
----------------------------------------------------------

Doppler is another code name for **cloudigrade**.

Or is **cloudigrade** a code name for Doppler?

``cloudigrade == Doppler`` for all intents and purposes. 😉


Running cloudigrade
===================

Please refer to the `shiftigrade repo <https://gitlab.com/cloudigrade/shiftigrade>`_ for up to date instructions on how to run cloudigrade. These instructions are prerequisite for setting up your developer environemnt.


Developer Environment
---------------------

Because **cloudigrade** is actually a suite of interacting services, setting up a development environment may require installing some or all of the following dependencies:

-  Python 3.8
-  `Docker <https://www.docker.com/community-edition#/download>`_
-  `tox <https://tox.readthedocs.io/>`_
-  `gettext <https://www.gnu.org/software/gettext/>`_
-  `PostgreSQL <https://www.postgresql.org/download/>`_
-  `AWS Command Line Interface <https://aws.amazon.com/cli/>`_


macOS dependencies
~~~~~~~~~~~~~~~~~~

The following commands should install everything you need:

.. code-block:: bash

    brew update
    brew install python@3.8 gettext awscli postgresql openssl curl-openssl
    brew link gettext --force


Linux dependencies
~~~~~~~~~~~~~~~~~~

We recommend developing on the latest version of Fedora. Follow the following commands to install the dependencies:

.. code-block:: bash

    sudo dnf install awscli gettext postgresql-devel librdkafka-devel -y


Python virtual environment
~~~~~~~~~~~~~~~~~~~~~~~~~~

We strongly encourage all developers to use a virtual environment to isolate **cloudigrade**\ 's Python package dependencies. You may use whatever tooling you feel comfortable with, but here are some initial notes for setting up with `poetry <https://python-poetry.org/docs/>`_:

.. code-block:: bash

    # install poetry
    pip install poetry

Once you have poetry installed, install our Python package requirements:

.. code-block:: sh

    poetry env remove
    poetry install

If you plan to run cloudigrade or Celery locally on macOS, the required ``pycurl`` package may fail to install or may install improperly despite ``poetry install`` appearing to complete successfully. You can verify that ``pycurl`` is installed correctly by simply importing it in a Python shell like this:

.. code-block:: sh

    poetry run python -c 'import pycurl'

If you see no output, everything is okay! Otherwise (e.g. "libcurl link-time ssl backend (openssl) is different from compile-time ssl backend (none/other)"), it may not have installed correctly. Try the following commands force it to rebuild and install with the openssl backend:

.. code-block:: sh

    brew update
    brew install openssl curl-openssl
    brew doctor  # ...and resolve any known problems.

    poetry run pip uninstall pycurl -y

    BREW_PATH=$(brew --prefix)
    export LDFLAGS="-L${BREW_PATH}/opt/openssl/lib/ -L${BREW_PATH}/opt/curl-openssl/lib -L${BREW_PATH}/opt/expat/lib/ -L${BREW_PATH}/lib -L/usr/lib/"
    export CFLAGS="-I${BREW_PATH}/opt/openssl/include/ -I${BREW_PATH}/opt/expat/include/ -I${BREW_PATH}/include/"
    export CPPFLAGS="-I${BREW_PATH}/opt/openssl/include/ -I${BREW_PATH}/opt/curl-openssl/include -I${BREW_PATH}/opt/expat/include/  -I${BREW_PATH}/include/"
    export PYCURL_CURL_CONFIG="${BREW_PATH}/opt/curl-openssl/bin/curl-config"
    export PYCURL_SSL_LIBRARY="openssl"

    poetry install
    poetry run python -c 'import pycurl'

If this resolves the import error, then you may also need to export all of those variables any time you have `tox` recreate its own virtual environments.

If using a system that has dnf, try the following commands:

.. code-block:: sh

    poetry run pip uninstall pycurl -y
    sudo dnf install openssl libcurl-devel
    export PYCURL_SSL_LIBRARY=openssl
    poetry install

Try the aforementioned import commands again, and all should be good. If not, kindly reach out to another cloudigrade developer to seek assistance!

After finishing the installation of dependencies you can grab a shell that uses the virtual environment by calling ``poetry shell``.


Configure AWS account credentials
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you haven't already, create an `Amazon Web Services <https://aws.amazon.com/>`_ account for **cloudigrade** to use for its AWS API calls. You will need the AWS access key ID, AWS secret access key, and region name where the account operates.

Use the AWS CLI to save that configuration to your local system:

.. code-block:: bash

    aws configure

You can verify that settings were stored correctly by checking the files it created in your ``~/.aws/`` directory.

AWS access for running **cloudigrade** inside a local OpenShift cluster must be enabled via environment variables. Set the following variables in your local environment *before* you start running in OpenShift. Values for these variables can be found in the files in your ``~/.aws/`` directory.

-  ``AWS_ACCESS_KEY_ID``
-  ``AWS_SECRET_ACCESS_KEY``
-  ``AWS_DEFAULT_REGION``
-  ``AWS_SQS_ACCESS_KEY_ID``
-  ``AWS_SQS_SECRET_ACCESS_KEY``
-  ``AWS_SQS_REGION``
-  ``AWS_NAME_PREFIX``

The values for ``AWS_`` keys and region may be reused for the ``AWS_SQS_`` variables. ``AWS_NAME_PREFIX`` should be set to something unique to your environment like ``${USER}-``.

You'll also need to set the SQS URL for the log analyzer for the variable ``AWS_CLOUDTRAIL_EVENT_URL``. This URL can be found in the queue details pane and will look something like ``https://sqs.us-east-1.amazonaws.com/977153484089/iwhite-cloudigrade-sqs-s3``


Configure Django settings module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For convenience, you may want to set the following environment variable:

.. code-block:: sh

    DJANGO_SETTINGS_MODULE=config.settings.local

If you do not set that variable, you may need to include the ``--settings=config.settings.local`` argument with any Django admin or management commands you run.


Configure AWS Policy for Capturing ECS Logs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For ECS to be able to write logs to CloudWatch, we'll need to create and assign it the ecs role.

First we'll create the policy.

- Open the IAM console at https://console.aws.amazon.com/iam/.
- In the navigation pane, choose Policies.
- Choose Create policy, JSON.
- Enter the following policy:
.. code-block:: json

    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "CloudigradePolicy",
                "Effect": "Allow",
                "Action": [
                    "ec2:DescribeImages",
                    "ec2:DescribeInstances",
                    "ec2:ModifySnapshotAttribute",
                    "ec2:DescribeSnapshotAttribute",
                    "ec2:DescribeSnapshots",
                    "ec2:CopyImage",
                    "ec2:CreateTags",
                    "ec2:DescribeRegions",
                    "cloudtrail:CreateTrail",
                    "cloudtrail:UpdateTrail",
                    "cloudtrail:PutEventSelectors",
                    "cloudtrail:DescribeTrails",
                    "cloudtrail:StartLogging",
                    "cloudtrail:StopLogging",
                ],
                "Resource": "*",
            }
        ],
    }

- Choose Review policy.
- On the Review policy page, enter ECS-CloudWatchLogs for the Name and choose Create policy.

Next, we will attach the policy.

- Open the IAM console at https://console.aws.amazon.com/iam/.
- In the navigation pane, choose Roles.
- Choose ecsInstanceRole.
- Choose Permissions, Attach policy.
- To narrow the available policies to attach, for Filter, type ECS-CloudWatchLogs.
- Check the box to the left of the ECS-CloudWatchLogs policy and choose Attach policy.

You'll be able to view CloudWatch Logs `here <https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logs:>`_, there will be a log group created for your ecs cluster.


Common commands
===============


Running Locally in OpenShift
----------------------------

All OC make commands are located in the `shiftigrade repository <https://gitlab.com/cloudigrade/shiftigrade>`_. Please clone and run all oc related make commands from there.
To start the local cluster run the following:

.. code-block:: bash

    cd <shiftigrade-repo>
    make oc-up

That will start a barebones OpenShift cluster that will persist configuration between restarts.

If you'd like to start the cluster, and deploy Cloudigrade along with supporting services run the following:

.. code-block:: bash

    # When deploying cloudigrade make sure you have AWS_ACCESS_KEY_ID and
    # AWS_SECRET_ACCESS_KEY set in your environment or the deployment will
    # not be able to talk to your AWS account
    cd <shiftigrade-repo>
    make oc-up-all

This will create the **ImageStream** to track **PostgreSQL:9.6**, template the objects for **cloudigrade**, and apply them to deploy **cloudigrade** and the supporting services. There is a chance that the deployment for **cloudigrade** will fail due to the db not being ready before the mid-deployment hook pod is being run. Simply run the following command to trigger a redemployment for **cloudigrade**:

.. code-block:: bash

    oc rollout latest cloudigrade

To stop the local cluster run the following:

.. code-block:: bash

    cd <shiftigrade-repo>
    make oc-down

Since all cluster information is preserved, you are then able to start the cluster back up with ``make oc-up`` and resume right where you have left off.

If you'd like to remove all your saved settings for your cluster, you can run the following:

.. code-block:: bash

    cd <shifitigrade-repo>
    make oc-clean

There are also other make targets available to deploy just the db or the project by itself, along with installing the templates and the ImageStream object.

Deploying in-progress code to OpenShift
---------------------------------------

If you'd like to deploy your in progress work to the local openshift cluster you can do so by pushing your code to your branch and deploying it with the following commands:

.. code-block:: bash

    # Specify the branch where your code is running as API_REPO_REF
    # and execute the following command
    export API_REPO_REF=1337-my-special-branch
    kontemplate template ocp/local.yaml | oc apply -f -

    # Then simply kick off a new build for cloudigrade
    oc start-build c-api

Now everytime you want your code redeployed you can push your code and trigger a new build using ``oc start-build <build-name>``.

Developing Locally with OpenShift
---------------------------------

By far the best way to develop **cloudigrade** is with it running locally, allowing you to benefit from quick code reloads and easy debugging while offloading running supporting services to OpenShift. There are multiple make targets available to make this process easy. For example to start a cluster and deploy the supporting services all you'd need to run is:

.. code-block:: bash

    cd <shiftigrade-repo>
    make oc-up-dev

This will start OpenShift and create deployments for the database. To then run the Django dev server run:

.. code-block:: bash

    make oc-run-dev

This will also forward ports for the database pod, making them accessible to the development server.

There are other commands available such as ``make oc-run-migrations`` which will run migrations for you against the database in the OpenShift cluster. ``make oc-forward-ports`` which will just forward the ports without starting the development server, allowing you to start it however you wish, and ``make oc-stop-forwarding-ports`` which will clean up the port forwards after you're done.


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

Troubleshooting the local OpenShift Cluster
-------------------------------------------

Occasionally when first deploying a cluster the PostgreSQL deployment will fail and crash loop, an easy way to resolve that is to kick off a new deployment of PostgreSQL with the following command:

.. code-block:: bash

    oc rollout latest dc/postgresql

If the cloudigrade deployment also failed because the database was not available when the migration midhook ran, you can retry that deployment with the following command:

.. code-block:: bash

    oc rollout retry dc/cloudigrade


Updating API Example Docs
-------------------------

To automatically update the API examples documentation, you need a database with current migrations applied but with no customer data in it. If you have deployed to a local OpenShift cluster, you should forward the database port so it can be accessed locally.

.. code-block:: sh

    make oc-forward-ports

Once the database is available, you may run the following Make target to generate the API examples documentation:

.. code-block:: sh

    make docs-api-examples

This will create many use-case-specific records in the database, simulate API calls through cloudigrade, and generate an updated document with the API calls. You should review any changes made by this command before adding and committing them to source control.

Generate a Spec File
--------------------

Generation of the spec file is handled by the same mechanism that serves our spec file via api, to ensure that they are the same. If you've recently made changes to the api and need to update the spec file, run the following command:

.. code-block:: sh

    make spec

Otherwise, if you'd simply like to verify that the spec is current, you can run the following:

.. code-block:: sh

    make spec-test


Authentication
==============

3Scale authentication is used to authenticate
users, for a local deployment, this means including a ``HTTP_X_RH_IDENTITY``
header in all requests.

API access is restricted to authenticated users.

For more information about this header see `examples. <./docs/rest-api-example.rst#Authorization>`_


When accessing any endpoint with the ``HTTP_X_RH_IDENTITY`` header,
if the user found in the header does not exist, it will be created.
It is also possible to programmatically create users on the command line,
for instance for testing. To create a user this way, use:

.. code-block:: sh

    make user
    # or the below command if you're running against cloudigrade in a local OpenShift cluster
    cd <shiftigrade-repo>
    make oc-user


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
.. |Updates| image:: https://pyup.io/repos/github/cloudigrade/cloudigrade/shield.svg
   :target: https://pyup.io/repos/github/cloudigrade/cloudigrade/
.. |Python 3| image:: https://pyup.io/repos/github/cloudigrade/cloudigrade/python-3-shield.svg
   :target: https://pyup.io/repos/github/cloudigrade/cloudigrade/
