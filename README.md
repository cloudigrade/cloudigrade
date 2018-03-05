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
    brew install python python3 pypy3 gettext awscli postgresql
    brew link gettext --force

Get into the cloudigrade project code:

    git clone git@github.com:cloudigrade/cloudigrade.git
    cd cloudigrade


## AWS account setup

Create an [AWS](https://aws.amazon.com/) account for Cloudigrade to use for its
AWS commands if you don't already have one. You will need the AWS access key ID,
AWS secret access key, and region name where the account operates.

Use the AWS CLI to save that configuration to your local system:

    aws configure

You can verify that settings were stored correctly by checking the files it
created in your `~/.aws/` directory.


## Python virtual environment setup

All of cloudigrade's dependencies should be stored in a virtual environment.
These instructions assume it is acceptable for you to use
[virtualenv](https://virtualenv.pypa.io/) and
[virtualenvwrapper](https://virtualenvwrapper.readthedocs.io/), but if you wish
to use another technology, that's your prerogative!

Install virtualenv and virtualenvwrapper with the system-level pip:

    pip2 install -U pip
    pip2 install -U virtualenvwrapper virtualenv

Add this command to your `~/.bash_profile` (assuming you use bash) or source it
each time you want to work with virtualenvwrapper:

    source /usr/local/bin/virtualenvwrapper.sh

Create a virtualenv for the project's dependencies:

    mkvirtualenv -p python3 cloudigrade

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


## Common commands

### Running

To run the application along with the postgres database run the following:

    make start-compose

If you'd like to run just the database, so you can run the application
on your local machine, use the following command:

    make start-db

To reinstantiate the docker psql db, run the following:

    make reinitdb

### Testing

To run all local tests as well as our code-quality checking commands:

    tox

If you wish to run _only_ the tests:

    make unittest

If you wish to run a higher-level suite of integration tests, see
[integrade](https://github.com/cloudigrade/integrade).


### Django management commands

To add an ARN:

    ./cloudigrade/manage.py add_account YOUR_ARN_GOES_HERE

