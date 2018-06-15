***********
cloudigrade
***********

|license| |Build Status| |codecov| |Updates| |Python 3|


What is cloudigrade?
====================

**cloudigrade** is an open-source suite of tools for tracking Linux distribution use (although chiefly targeting RHEL) in public cloud platforms. **cloudigrade** actively checks a user's account in a particular cloud for running instances, tracks when instances are powered on, determines what Linux distributions are installed on them, and provides the ability to generate reports to see how long different distributions have run in a given window.


What is this "Doppler" I see referenced in various places?
----------------------------------------------------------

Doppler is another code name for **cloudigrade**.

Or is **cloudigrade** a code name for Doppler?

``cloudigrade == Doppler`` for all intents and purposes. 😉


Running cloudigrade
===================

Please refer to the `shiftigrade repo <https://github.com/cloudigrade/shiftigrade#running-cloudigrade>`_ for up to date instructions on how to run cloudigrade. These instructions are prerequisite for setting up your developer environemnt.


Developer Environment
---------------------

Because **cloudigrade** is actually a suite of interacting services, setting up a development environment may require installing some or all of the following dependencies:

-  Python (one of the versions we support)
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
    brew install python gettext awscli postgresql openssl
    brew link gettext --force


Linux dependencies
~~~~~~~~~~~~~~~~~~

We recommend developing on the latest version of Fedora. Follow the following commands to install the dependencies:

.. code-block:: bash

    sudo dnf install awscli gettext postgresql-devel -y


Python virtual environment
~~~~~~~~~~~~~~~~~~~~~~~~~~

We strongly encourage all developers to use a virtual environment to isolate **cloudigrade**\ 's Python package dependencies. You may use whatever tooling you feel confortable with, but here are some initial notes for setting up with `virtualenv <https://pypi.python.org/pypi/virtualenv>`_ and `virtualenvwrapper <https://pypi.python.org/pypi/virtualenvwrapper>`_:

.. code-block:: bash

    # install virtualenv and virtualenvwrapper
    pip install -U pip
    pip install -U virtualenvwrapper virtualenv
    echo "source \"$(brew --prefix)/bin/virtualenvwrapper.sh\"" >> ~/.bash_profile
    source $(brew --prefix)/bin/virtualenvwrapper.sh

    # create the environment
    mkvirtualenv cloudigrade

    # activate the environment
    workon cloudigrade

Once you have an environment set up, install our Python package requirements:

.. code-block:: sh

    pip install -U pip wheel tox
    pip install -r requirements/local.txt


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
-  ``AWS_SQS_QUEUE_NAME_PREFIX``

The values for ``AWS_`` keys and region may be reused for the ``AWS_SQS_`` variables. ``AWS_SQS_QUEUE_NAME_PREFIX`` should be set to something unique to your environment like ``${USER}-``.


Configure Django settings module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For convenience, you may want to set the following environment variable:

.. code-block:: sh

    DJANGO_SETTINGS_MODULE=config.settings.local

If you do not set that variable, you may need to include the ``--settings=config.settings.local`` argument with any Django admin or management commands you run.


Common commands
===============


Running Locally in OpenShift
----------------------------

To start the local cluster run the following:

.. code-block:: bash

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

    make oc-down

Since all cluster information is preserved, you are then able to start the cluster back up with ``make oc-up`` and resume right where you have left off.

If you'd like to remove all your saved settings for your cluster, you can run the following:

.. code-block:: bash

    make oc-clean

There are also other make targets available to deploy just the db or the project by itself, along with installing the templates and the ImageStream object.

Deploying in-progress code to OpenShift
---------------------------------------

If you'd like to deploy your in progress work to the local openshift cluster you can do so by pushing your code to your branch and deploying it with the following commands:

.. code-block:: bash

    # Specify the branch where your code is running, use CLOUDIGRADE_REPO_REF
    # for Cloudigrade and FRONTIGRADE_REPO_REF for frontigrade and execute
    # the following command
    export CLOUDIGRADE_REPO_REF=1337-my-special-branch
    export FRONTIGRADE_REPO_REF=123-the-best-code
    kontemplate template ocp/local.yaml | oc apply -f -

    # Then simply kick off a new build for cloudigrade
    oc start-build cloudigrade-api
    # or frontigrade
    oc start-build frontigrade

Now everytime you want your code redeployed you can push your code and trigger a new build using ``oc start-build <build-name>``.

Developing Locally with OpenShift
---------------------------------

By far the best way to develop **cloudigrade** is with it running locally, allowing you to benefit from quick code reloads and easy debugging while offloading running supporting services to OpenShift. There are multiple make targets available to make this process easy. For example to start a cluster and deploy the supporting services all you'd need to run is:

.. code-block:: bash

    make oc-up-dev

This will start OpenShift and create deployments for the database. To then run the Django dev server run:

.. code-block:: bash

    make oc-run-dev

This will also forward ports for the database pod, making them accessible to the development server.

There are other commands available such as ``make oc-run-migration`` which will run migrations for you against the database in the OpenShift cluster. ``make oc-forward-ports`` which will just forward the ports without starting the development server, allowing you to start it however you wish, and ``make oc-stop-forwarding-ports`` which will clean up the port forwards after you're done.


Testing
-------

To run all local tests as well as our code-quality checking commands:

.. code-block:: sh

    tox

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


Authentication
==============

Django Rest Framework token authentication is used to authenticate
users, with djoser (http://djoser.readthedocs.io/en/stable/index.html)
for user account management and login/logout. API access is restricted
to authenticated users. All API calls require an Authorization header:

.. code-block::

    Authorization: "Token `auth_token`"

In addition to the djoser frontend, it is possible to programmatically
create users on the command line, for instance for testing. To create
a user this way, use:

.. code-block:: sh

    make user
    # or the below command if you're running against cloudigrade in a local OpenShift cluster
    make oc-user

To then generate an auth token, run the make command:

.. code-block:: sh

    make user-authenticate
    # or the below command if you're running against cloudigrade in a local OpenShift cluster
    make oc-user-authenticate

This auth token can be supplied in the Authorization header.


Message Broker
==============

Amazon SQS is used to broker messages between **cloudigrade**, Celery workers, and houndigrade.

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
