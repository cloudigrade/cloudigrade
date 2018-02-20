# Developing cloudigrade

This document provides instructions for setting up cloudigrade's development
environment and some commands for testing and running it.

## Local system setup (macOS)

Install [homebrew](https://brew.sh/):

    /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

Use homebrew to install modern Python, the AWS CLI, and gettext:

    brew update
    brew install python python3 pypy3 gettext awscli
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
