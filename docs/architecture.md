# cloudigrade Architecture Document

## Overview

cloudigrade is a service that monitors, tracks, and reports on RHEL instance activity in public clouds for Red Hat customers. See [README.md](https://github.com/cloudigrade/cloudigrade/blob/master/README.rst) and [Adding sources for public cloud metering](https://access.redhat.com/documentation/en-us/subscription_central/2021/html/getting_started_with_the_subscriptions_service/assembly-adding-sources-publiccloudmetering) for more general information.

## Technology Stack

cloudigrade is written in [Python 3](https://docs.python.org/3/) using [Django](https://www.djangoproject.com/) with [Django Rest Framework](https://www.django-rest-framework.org/) for HTTP APIs and model handling, [Celery](https://docs.celeryproject.org/) for asynchronous task processing, and [Poetry](https://python-poetry.org/) for managing its Python package dependencies. See cloudigrade's [Dockerfile](https://github.com/cloudigrade/cloudigrade/blob/master/Dockerfile) and [pyproject.toml](https://github.com/cloudigrade/cloudigrade/blob/master/pyproject.toml) for more details. cloudigrade records its data to a [PostgreSQL](https://www.postgresql.org/) database, typically pooled through [postigrade](https://github.com/cloudigrade/postigrade/) (a containerized [PgBouncer](https://www.pgbouncer.org/)).

cloudigrade deploys to AppSRE-managed projects in OpenShift using [app-interface](https://gitlab.cee.redhat.com/service/app-interface/) and [Clowder](https://github.com/RedHatInsights/clowder/) as defined by scripts and configs in [deployment](https://github.com/cloudigrade/cloudigrade/tree/master/deployment). When deployed to OpenShift using those tools, cloudigrade has several running deployments including:

- cloudigrade-api: the Django HTTP web service (scaled to many pods)
- cloudigrade-worker: asynchronous Celery workers (scaled to many pods)
- cloudigrade-beat: Celery beat for scheduled tasks (only *exactly one* pod)
- cloudigrade-listener: Kafka message queue reader (only *exactly one* pod)
- postigrade: PgBouncer proxy/pool to AWS RDS (scaled to many pods)

Upon deployment, cloudigrade automatically configures various resources for its own AWS account using [Ansible](https://www.ansible.com/) playbooks defined in [playbooks](https://github.com/cloudigrade/cloudigrade/tree/master/deployment/playbooks).

## Dependencies

cloudigrade has the following operational dependencies. See also [app.yml](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/cloudigrade/app.yml).

- Red Hat/internal:
  - [OpenShift](https://openshift.com) ([status](https://status.pro.openshift.com/)) service hosting.
  - [Quay.io](https://quay.io) ([status](https://status.quay.io/)) as contianer registry.
  - [App-SRE Jenkins](ci.ext.devshift.net) for various build jobs.
  - [app-interface](https://gitlab.cee.redhat.com/service/app-interface/) to define and trigger OpenShift configuration changes.
  - [Clowder](https://github.com/RedHatInsights/clowder/) operator running in OpenShift to manage deployments.
  - [postigrade](https://github.com/cloudigrade/postigrade/) to proxy and pool database connections to AWS RDS.
  - [Sources API](https://github.com/RedHatInsights/sources-api/) as primary source of customer cloud accounts.
  - Platform-managed Kafka for sending and receiving messages between cloudigrade and other platform services.
- External:
  - [GitHub cloudigrade project](https://github.com/cloudigrade/) for source code repositories and development.
  - [GitHub bonfire repo](https://github.com/RedHatInsights/bonfire) for PR check bootstrap.
  - [Sentry.io](https://sentry.io/) ([status](https://status.sentry.io/)) for error issue and performance transaction monitoring
  - [Amazon Web Services (AWS)](https://aws.amazon.com/) ([status](https://status.aws.amazon.com/))
    - AWS customer account(s) to:
      - configure CloudTrail monitoring
      - describe EC2 resources
      - copy EC2 image snapshots
    - AWS cloudigrade account to:
      - describe known EC2 instance type definitions
      - use SQS queues for various processes
      - establish sessions with customer accounts (via STS)
      - read customer CloudTrail activity logs from S3
      - inspect EC2 images via [houndigrade](https://github.com/cloudigrade/houndigrade/) in EC2 cloud-init
    - AWS Red Hat SRE account for SRE-managed RDS PSQL database and CloudWatch logging.
  - [Microsoft Azure](https://azure.microsoft.com/) ([status](https://status.azure.com/)):
    - cloudigrade subscription to:
      - describe VM resource capability definitions



## Runtime Dependencies Overview

<img src="images/cloudigrade-arch-dependencies.svg">

## AWS API Interactions Overview

<img src="images/cloudigrade-arch-aws.svg">
