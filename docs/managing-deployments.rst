********************************
Managing cloudigrade deployments
********************************

This document highlights some of the key methods of managing the cloudigrade installation as managed and run by its maintainers at Red Hat.


Deploying cloudigrade and frontigrade
=====================================

`cloudigrade <https://gitlab.com/cloudigrade/cloudigrade/>`_ is deployed to the Insights OSD cluster using e2e-deploy. Once code is merged to master it is deployed to CI and QA, then it's on to QE to promote the image to Stage, and then finally Prod.


Deploying houndigrade
=====================

`houndigrade <https://gitlab.com/cloudigrade/houndigrade/>`_ is not explicitly deployed because it is not a long-running service. Instead the GitLab CI pipeline creates and tags Docker images and stores them to `houndigrade's container registry <https://gitlab.com/cloudigrade/houndigrade/container_registry>`_. When a commit lands on master and tests pass, the ``latest`` tag is updated with the latest built master image in the registry. When a tag lands on master and tests pass, a matching tag is also created in the registry.

During the inspection process, cloudigrade sends a task to ECS that includes the specific image tag to use. This tag is configured from an environment variable ``HOUNDIGRADE_ECS_IMAGE_TAG``, and its value is set via `e2e-deploy <https://github.com/RedHatInsights/e2e-deploy/>`_ configs. When we tag a new version of houndigrade, we must update the version defined in e2e-deploy so cloudigrade will know to use it.

Look for the ``AWS_HOUNDIGRADE_ECS_IMAGE_TAG`` values defined in these configs:

- https://github.com/RedHatInsights/e2e-deploy/blob/master/templates/cloudigrade/env/ci.yml
- https://github.com/RedHatInsights/e2e-deploy/blob/master/templates/cloudigrade/env/qa.yml
- https://github.com/RedHatInsights/e2e-deploy/blob/master/templates/cloudigrade/env/stage.yml
- https://github.com/RedHatInsights/e2e-deploy/blob/master/templates/cloudigrade/env/prod.yml


AWS Supporting Infrastructure
=============================

Test, stage, and prod environments have supporting infrastructure in AWS accounts for the following services:

- SQS for various message queues
- S3 buckets to hold CloudTrail log files
- RDS for Postgresql
- ECS for houndigrade

Under normal operation, no users should interact directly with these backing services, and you risk corrupting the state of the system if you do.

Test and stage AWS services share a single AWS account. Prod AWS services live in its own separate AWS account. If you believe you need access to these AWS accounts, please contact your manager.
