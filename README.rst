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

We do not yet have concise setup notes for running **cloudigrade**, and we currently require setting up a complete development envirionment. Watch this space for changes in the future, but for now, please read the next "Developer Environment" section.


Developer Environment
---------------------

Because **cloudigrade** is actually a suite of interacting services, setting up a development environment may require installing some or all of the following dependencies:

-  Python (one of the versions we support)
-  `Docker <https://www.docker.com/community-edition#/download>`_
-  `docker-compose <https://docs.docker.com/compose/install/>`_
-  `tox <https://tox.readthedocs.io/>`_
-  `gettext <https://www.gnu.org/software/gettext/>`_
-  `PostgreSQL <https://www.postgresql.org/download/>`_
-  `AWS Command Line Interface <https://aws.amazon.com/cli/>`_


macOS dependencies
~~~~~~~~~~~~~~~~~~

We encourage macOS developers to use `homebrew <https://brew.sh/>`_ to install and manage these dependencies. The following commands should install everything you need:

.. code-block:: bash

    /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
    brew update
    brew install python pypy3 gettext awscli postgresql socat
    brew link gettext --force
    # We need to install a specific version of docker since newer ones have a bug around the builtin proxy
    brew cask install https://raw.githubusercontent.com/caskroom/homebrew-cask/61f1d33be340e27b91f2a5c88da0496fc24904d3/Casks/docker.rb

After installing Docker, open it, navigate to Preferences -> General and uncheck ``Automatically check for updates`` if it is checked, then navigate to Preferences -> Daemon. There add ``172.30.0.0/16`` to the list of insecure registries, then click ``Apply and Restart``.

We currently use Openshift 3.7.X in production, so we need a matching openshift client.

.. code-block:: bash

    brew install https://raw.githubusercontent.com/Homebrew/homebrew-core/9d190ab350ce0b0d00d4968fed4b9fbe68a318ef/Formula/openshift-cli.rb
    brew pin openshift-cli

Linux dependencies
~~~~~~~~~~~~~~~~~~

We recommend developing on the latest version of Fedora. Follow the following commands to install the dependencies:

.. code-block:: bash

    # DNF Install AWS-CLI, Docker, PyPy3, and gettext
    sudo dnf install awscli docker pypy3 gettext postgresql-devel -y
    # Install an appropriate version of the OpenShift Client
    wget -O oc.tar.gz https://github.com/openshift/origin/releases/download/v3.7.2/openshift-origin-client-tools-v3.7.2-282e43f-linux-64bit.tar.gz
    tar -zxvf oc.tar.gz
    cp openshift-origin-client-tools-v3.7.2-282e43f-linux-64bit/oc ~/bin
    # Allow interaction with Docker without root
    sudo groupadd docker && sudo gpasswd -a ${USER} docker
    newgrp docker
    # Configure Insecure-Registries in Docker
    sudo cat > /etc/docker/daemon.json <<EOF
    {
       "insecure-registries": [
         "172.30.0.0/16"
       ]
    }
    EOF
    sudo systemctl daemon-reload
    sudo systemctl restart docker
    # Configure firewalld
    sudo sysctl -w net.ipv4.ip_forward=1
    sudo firewall-cmd --permanent --new-zone dockerc
    sudo firewall-cmd --permanent --zone dockerc --add-source $(docker network inspect -f "{{range .IPAM.Config }}{{ .Subnet }}{{end}}" bridge)
    sudo firewall-cmd --permanent --zone dockerc --add-port 8443/tcp
    sudo firewall-cmd --permanent --zone dockerc --add-port 53/udp
    sudo firewall-cmd --permanent --zone dockerc --add-port 8053/udp
    sudo firewall-cmd --reload


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

AWS access for running **cloudigrade** inside Docker must be enabled via environment variables. Set the following variables in your local environment *before* you start running in Docker containers. Values for these variables can be found in the files in your ``~/.aws/`` directory.

-  ``AWS_ACCESS_KEY_ID``
-  ``AWS_SECRET_ACCESS_KEY``
-  ``AWS_DEFAULT_REGION``


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
    # AWS_SECRET_ACCESS_KEY set in your environment or the deployment will fail
    make oc-up-all

This will create the **ImageStream** to track **PostgreSQL:9.6**, create the templates for **RabbitMQ** and **cloudigrade**, and finally use the templates to create all the objects necessary to deploy **cloudigrade** and the supporting services. There is a chance that the deployment for **cloudigrade** will fail due to the db not being ready before the mid-deployment hook pod is being run. Simply run the following command to trigger a redemployment for **cloudigrade**:

.. code-block:: bash

    oc rollout latest cloudigrade

To stop the local cluster run the following:

.. code-block:: bash

    make oc-down

Since all cluster information is preserved, you are then able to start the cluster back up with ``make oc-up`` and resume right where you have left off.

If you'd like to remove all your saved settings for your cluster, you can run the following:

.. code-block:: bash

    make oc-clean

There are also other make targets available to deploy just the queue, db, or the project by itself, along with installing the templates and the ImageStream object.

Deploying in-progress code to OpenShift
---------------------------------------

If you'd like to deploy your in progress work to the local openshift cluster you can do so with the following commands:

.. code-block:: bash

    # Assuming the cluster is up and running with cloudigrade and services already deployed
    # First create a route to the internal registry
    make oc-create-registry-route

    # Build and Push Cloudigrade to the internal registry
    make oc-build-and-push-cloudigrade

Repeat the above command ``make oc-build-and-push-cloudigrade`` as often as you need to re-deploy your code.

Developing Locally with OpenShift
---------------------------------

By far the best way to develop **cloudigrade** is with it running locally, allowing you to benefit from quick code reloads and easy debugging while offloading running supporting services to OpenShift. There are multiple make targets available to make this process easy. For example to start a cluster and deploy the supporting services all you'd need to run is:

.. code-block:: bash

    make oc-up-dev

This will start OpenShift and create deployments for the database and queue. To then run the Django dev server run:

.. code-block:: bash

    make oc-run-dev

This will also forward ports for the database and queue pods, making them accessible to the development server.

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

If your cloudigrade deployment failed because you didn't have ``AWS_ACCESS_KEY_ID`` or ``AWS_SECRET_ACCESS_KEY`` set, you don't have to torch everything and start over after setting them, you can just recreate the cloudigrade deployment with the following command:

.. code-block:: bash

    make oc-create-cloudigrade


Authentication
==============

Django Rest Framework token authentication is used to authenticate users. API access is restricted to authenticated users. All API calls require an Authorization header:

.. code-block::

    Authorization: "Token `auth_token`"

To create a user run the following make command and follow the prompts:

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

RabbitMQ is used to broker messages between **cloudigrade** and inspectigrade services. There are multiple Python packages available to interact with RabbitMQ; the officially recommended packaged is `Pika <https://pika.readthedocs.io/en/latest/>`_. Both services serve as producers and consumers of the message queue.

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
