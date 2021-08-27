#!/bin/bash

export APP_NAME="cloudigrade"  # name of app-sre "application" folder this component lives in
export COMPONENT_NAME="cloudigrade"  # name of app-sre "resourceTemplate" in deploy.yaml for this component
export IMAGE="quay.io/cloudservices/cloudigrade"  # the image location on quay

export IQE_PLUGINS="cloudigrade"  # name of the IQE plugin for this APP
export IQE_MARKER_EXPRESSION="cloudigrade_smoke"  # This is the value passed to pytest -m
export IQE_FILTER_EXPRESSION=""  # This is the value passed to pytest -k
export IQE_CJI_TIMEOUT="30m"  # This is the time to wait for smoke test to complete or fail

# Install bonfire repo/initialize
CICD_URL=https://raw.githubusercontent.com/RedHatInsights/bonfire/master/cicd
curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh

# Build the image and push to quay
source $CICD_ROOT/build.sh

# Run the unit tests with an ephemeral db
# source $APP_ROOT/unit_test.sh

# Deploy rbac to an ephemeral namespace for testing
source $CICD_ROOT/deploy_ephemeral_env.sh

# Run smoke tests with ClowdJobInvocation
# source $CICD_ROOT/cji_smoke_test.sh
