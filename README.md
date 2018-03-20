# cloudigrade

[![license](https://img.shields.io/github/license/cloudigrade/cloudigrade.svg)]()
[![Build Status](https://travis-ci.org/cloudigrade/cloudigrade.svg?branch=master)](https://travis-ci.org/cloudigrade/cloudigrade)
[![codecov](https://codecov.io/gh/cloudigrade/cloudigrade/branch/master/graph/badge.svg)](https://codecov.io/gh/cloudigrade/cloudigrade)
[![Updates](https://pyup.io/repos/github/cloudigrade/cloudigrade/shield.svg)](https://pyup.io/repos/github/cloudigrade/cloudigrade/)
[![Python 3](https://pyup.io/repos/github/cloudigrade/cloudigrade/python-3-shield.svg)](https://pyup.io/repos/github/cloudigrade/cloudigrade/)

# What is cloudigrade?

cloudigrade is an open-source suite of tools for tracking Linux distribution
use (although chiefly targeting RHEL) in public cloud platforms. cloudigrade
actively checks a user's account in a particular cloud for running instances,
tracks when instances are powered on, determines what Linux distributions are
installed on them, and provides the ability to generate reports to see how
long different distributions have run in a given window.

## What is this "Doppler" I see referenced in various places?

Doppler is another code name for cloudigrade.

Or is cloudigrade a code name for Doppler?

`cloudigrade == Doppler` for all intents and purposes. 😉


# Developing cloudigrade

This document provides instructions for setting up cloudigrade's development
environment and some commands for testing and running it.

## Local system setup (macOS)

Install [homebrew](https://brew.sh/):

    /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

Use homebrew to install modern Python, the AWS CLI, and gettext:

    brew update
    brew install python pypy3 gettext awscli postgresql
    brew link gettext --force

Get into the cloudigrade project code:

    git clone git@github.com:cloudigrade/cloudigrade.git
    cd cloudigrade

Need to run cloudigrade? Use docker-compose!

    make start-compose

This will also mount the `./cloudigrade` folder inside the container, so you can
continue working on code and it will auto-reload in the container. AWS Access
within Docker is handled via environment variables. See the AWS account setup
section for details.

## AWS account setup

Create an [AWS](https://aws.amazon.com/) account for Cloudigrade to use for its
AWS commands if you don't already have one. You will need the AWS access key ID,
AWS secret access key, and region name where the account operates.

Use the AWS CLI to save that configuration to your local system:

    aws configure

You can verify that settings were stored correctly by checking the files it
created in your `~/.aws/` directory.

AWS Access within Docker is enabled via environment variables. Set the following
variables in your local environment prior to running make start-compose. Values
for these variables can be found in your `~/.aws/` directory.

    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION


## Python virtual environment setup

All of cloudigrade's dependencies should be stored in a virtual environment.
These instructions assume it is acceptable for you to use
[virtualenv](https://virtualenv.pypa.io/) and
[virtualenvwrapper](https://virtualenvwrapper.readthedocs.io/), but if you wish
to use another technology, that's your prerogative!

Install virtualenv and virtualenvwrapper with the system-level pip:

    pip3 install -U pip
    pip3 install -U virtualenvwrapper virtualenv

Add this command to your `~/.bash_profile` (assuming you use bash) or source it
each time you want to work with virtualenvwrapper:

    source /usr/local/bin/virtualenvwrapper.sh

Create a virtualenv for the project's dependencies:

    mkvirtualenv cloudigrade

If you already have a virtualenv or are working in a _new_ shell, activate it:

    workon cloudigrade

Install project dependencies:

    pip install -U pip wheel tox
    pip install -r requirements/local.txt


## Django setup

Set these environment variables for Django or else you will need to pass them to
the commands manually:

    export DJANGO_SETTINGS_MODULE=config.settings.local
    export PYTHONPATH=$(pwd)/cloudigrade

## Coding Style

As a required CI build step, we use `tox -e flake8` to run [flake8](https://pypi.python.org/pypi/flake8) with mostly standard settings plus the following plugins to ensure consistent coding style across the project:

- [flake8-docstrings](https://pypi.python.org/pypi/flake8-docstrings)
- [flake8-quotes](https://pypi.python.org/pypi/flake8-quotes)
- [flake8-import-order](https://pypi.python.org/pypi/flake8-import-order)

Imports must follow the `pycharm` style. If you are using PyCharm as your IDE, you can coerce it to use a compliant behavior by configuring your settings as follows:

![](docs/pycharm-settings-imports.png)

Alternatively, you may use the command-line tool [isort](https://pypi.python.org/pypi/isort) which has default settings that match closely enough for cloudigrade. `isort` can be used to automatically clean up imports across many files, but please manually review its changes before committing to ensure that there are no unintended side-effects. Example usage:

    # view diff of suggested changes
    isort -df -rc ./cloudigrade/

    # apply all changes to files
    isort -rc ./cloudigrade/


## Common commands

### Running

To run the application along with the postgres database and queue
run the following:

    make start-compose

If you would like to run just the database, so you can run the application
on your local machine, use the following command:

    make start-db

To reinstantiate the docker psql db, run the following:

    make reinitdb

If you would like to run just the queue, so you can interact with the queue on
your local machine, use the following command:

    make start-queue

### Testing

To run all local tests as well as our code-quality checking commands:

    tox

If you wish to run _only_ the tests:

    make unittest

If you wish to run a higher-level suite of integration tests, see
[integrade](https://github.com/cloudigrade/integrade).


### Authentication

Django Rest Framework token authentication is used to authenticate users. API
access is restricted to authenticated users. All API calls require an
Authorization header:

    Authorization: "Token `auth_token`"

To create a user run the following make command and follow the prompts:

    make user

To then generate an auth token, run the make command:

    make user-authenticate

This auth token can be supplied in the Authorization header.

### Message Broker

RabbitMQ is used to broker messages between cloudigrade and inspectigrade
services. There are multiple Python packages available to interact with
RabbitMQ; the officially recommended packaged is [Pika](https://pika.readthedocs.io/en/latest/). Both services serve as producers and consumers of the message queue.
The cloudigrade docker-compose file requires that a password environment
variable be set for the RabbitMQ user. Make sure that the following has been
set in your local environment before starting

    RABBITMQ_DEFAULT_PASS

The RabbitMQ container can persist message data in the cloudigrade directory.
To purge this data use

    make remove-compose-queue
