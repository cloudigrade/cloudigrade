********************************
Managing cloudigrade deployments
********************************

This document highlights some of the key methods of managing the cloudigrade installation as managed and run by its maintainers at Red Hat.


Deploying cloudigrade and frontigrade
=====================================

`cloudigrade <https://gitlab.com/cloudigrade/cloudigrade/pipelines>`_ and `frontigrade <https://gitlab.com/cloudigrade/frontigrade/pipelines>`_ are deployed to the Insights OSD account using typical GitLab CI pipelines.

- Test: When a commit lands on master and tests pass, it automatically deploys to the test environment (`test.cloudigra.de <https://test.cloudigra.de>`_).
- Stage: When a tag lands on master and tests pass, it automatically deploys to the stage environment (`stage.cloudigra.de <https://stage.cloudigra.de>`_).
- Prod: In the tag's pipeline, after the stage deployment is a final manual step named "Deploy to Production". Clicking the proceed button for this step will deploy to the production environment (`www.cloudigra.de <https://www.cloudigra.de>`_).

cloudigrade and frontigrade deployments are not technically dependent on each other, and they can be deployed in any order or simultaeously. Just keep in mind any functional dependencies between the two (e.g. do we need a new API to be available before a new UI element exists?).


Deploying houndigrade
=====================

`houndigrade <https://gitlab.com/cloudigrade/houndigrade/>`_ is not explicitly deployed because it is not a long-running service. Instead the GitLab CI pipeline creates and tags Docker images and stores them to `houndigrade's container registry <https://gitlab.com/cloudigrade/houndigrade/container_registry>`_. When a commit lands on master and tests pass, the ``latest`` tag is updated with the latest built master image in the registry. When a tag lands on master and tests pass, a matching tag is also created in the registry.

During the inspection process, cloudigrade sends a task to ECS that includes the specific image tag to use. This tag is configured from an environment variable ``HOUNDIGRADE_ECS_IMAGE_TAG``, and its value is set via `shiftigrade <https://gitlab.com/cloudigrade/shiftigrade/>`_ configs. When we tag a new version of houndigrade, we must update the version defined in shiftigrade so cloudigrade will know to use it.

Look for the ``.houndigrade.ecs.imageTag`` values defined in these configs:

- https://gitlab.com/cloudigrade/shiftigrade/blob/master/ocp/test.yaml
- https://gitlab.com/cloudigrade/shiftigrade/blob/master/ocp/stage.yaml
- https://gitlab.com/cloudigrade/shiftigrade/blob/master/ocp/prod.yaml


Accessing test/stage/prod internals
===================================

Test, stage, and prod environments for cloudigrade as managed by Red Hat run in separate projects under the Insights OpenShift Dedicated account. Normal operation of cloudigrade should not require any direct interaction with the OSD projects. Deployments from GitLab CI should automatically handle any migrations and configuration changes.

If you wish to access the projects directly via the ``oc`` CLI:

#. `Log in to Insights OSD <https://console.insights.openshift.com/console/>`_.
#. Click your username in the header and click "Copy Login Command".
#. Open a local terminal, paste the copied command, and execute it.
#. Run ``oc projects`` to see a list of projects you have access to.
#. Run ``oc project PROJECTNAME`` using the name of the project you want to use.


To access OSD environment's Django admin
----------------------------------------

Please exercise **extreme caution** with the Django admin in these environments. Only use this tool if absolutely necessary.

#. ``oc port-forward $(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=cloudigrade-api | awk '{print $1}') 8080``
#. ``open "http://127.0.0.1:8080/admin/"``
#. Use your superuser credentials to proceed.


To access OSD environment's Django shell
----------------------------------------

Please exercise **extreme caution** with the Django shell in these environments. Only use this tool as a last resort after trying to use Django admin.

#. ``oc rsh -c cloudigrade-api $(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=cloudigrade-api | awk '{print $1}') scl enable rh-python36 -- python manage.py shell``
#. Be careful what you type.


AWS Supporting Infrastructure
=============================

Test, stage, and prod environments have supporting infrastructure in AWS accounts for the following services:

- SQS for various message queues
- S3 buckets to hold CloudTrail log files
- RDS for Postgresql
- ECS for houndigrade

Under normal operation, no users should interact directly with these backing services, and you risk corrupting the state of the system if you do.

Test and stage AWS services share a single AWS account. Prod AWS services live in its own separate AWS account. If you believe you need access to these AWS accounts, please contact your manager.
