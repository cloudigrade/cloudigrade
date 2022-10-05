#!/bin/bash

# Clowder Config
export APP_NAME="cloudigrade"  # name of app-sre "application" folder this component lives in
export COMPONENT_NAME="cloudigrade"  # name of app-sre "resourceTemplate" in deploy.yaml for this component
export IMAGE="quay.io/cloudservices/cloudigrade"  # the image location on quay
export DEPLOY_TIMEOUT="600"  # give components a bit more time to deploy

# IQE Plugin Config
export IQE_PLUGINS="cloudmeter"  # name of the IQE plugin for this APP
export IQE_MARKER_EXPRESSION="smoke"  # This is the value passed to pytest -m
export IQE_FILTER_EXPRESSION=""  # This is the value passed to pytest -k
export IQE_CJI_TIMEOUT="23m"  # This is the time to wait for smoke test to complete or fail

# Install bonfire repo/initialize
CICD_URL=https://raw.githubusercontent.com/RedHatInsights/bonfire/master/cicd
curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh

# Build the image and push to quay
source $CICD_ROOT/build.sh

# Deploy cloudigrade to an ephemeral namespace for testing
source ${CICD_ROOT}/_common_deploy_logic.sh
export NAMESPACE=$(bonfire namespace reserve --pool "real-managed-kafka")

oc get secret/cloudigrade-aws -o json -n ephemeral-base | jq -r '.data' > aws-creds.json
oc get secret/cloudigrade-azure -o json -n ephemeral-base | jq -r '.data' > azure-creds.json

AWS_ACCESS_KEY_ID=$(jq -r '."aws-access-key-id"' < aws-creds.json)
AWS_SECRET_ACCESS_KEY=$(jq -r '."aws-secret-access-key"' < aws-creds.json)
AWS_SQS_ACCESS_KEY_ID=$(jq -r '."aws-sqs-access-key-id"' < aws-creds.json)
AWS_SQS_SECRET_ACCESS_KEY=$(jq -r '."aws-sqs-secret-access-key"' < aws-creds.json)
AZURE_CLIENT_ID=$(jq -r '."client_id"' < azure-creds.json)
AZURE_CLIENT_SECRET=$(jq -r '."client_secret"' < azure-creds.json)
AZURE_SP_OBJECT_ID=$(jq -r '."sp_object_id"' < azure-creds.json)
AZURE_SUBSCRIPTION_ID=$(jq -r '."subscription_id"' < azure-creds.json)
AZURE_TENANT_ID=$(jq -r '."tenant_id"' < azure-creds.json)
CW_AWS_REGION_NAME=$(echo -n "us-east-1" | base64)
CLOUDIGRADE_CW_LOG_GROUP=$(echo -n "ephemeral-${NAMESPACE}" | base64)
CLOUDIGRADE_CW_RETENTION_DAYS="3"
CLOUDIGRADE_ENVIRONMENT="ephemeral-pr-check"

bonfire deploy \
    ${APP_NAME} \
    --source=appsre \
    --ref-env insights-stage \
    --set-template-ref ${COMPONENT_NAME}=${GIT_COMMIT} \
    --set-template-ref postigrade=master \
    --set-image-tag ${IMAGE}=${IMAGE_TAG} \
    --namespace ${NAMESPACE} \
    --timeout ${DEPLOY_TIMEOUT} \
    ${COMPONENTS_ARG} \
    ${COMPONENTS_RESOURCES_ARG} \
    --set-parameter rbac/MIN_REPLICAS=1 \
    --set-parameter sources-api/SOURCES_ENV=ci \
    --set-parameter cloudigrade/CLOUDIGRADE_ENVIRONMENT="${CLOUDIGRADE_ENVIRONMENT}" \
    --set-parameter cloudigrade/AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
    --set-parameter cloudigrade/AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY} \
    --set-parameter cloudigrade/AWS_SQS_ACCESS_KEY_ID=${AWS_SQS_ACCESS_KEY_ID} \
    --set-parameter cloudigrade/AWS_SQS_SECRET_ACCESS_KEY=${AWS_SQS_SECRET_ACCESS_KEY} \
    --set-parameter cloudigrade/CW_AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
    --set-parameter cloudigrade/CW_AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY} \
    --set-parameter cloudigrade/CW_AWS_REGION_NAME=${CW_AWS_REGION_NAME} \
    --set-parameter cloudigrade/CLOUDIGRADE_CW_LOG_GROUP=${CLOUDIGRADE_CW_LOG_GROUP} \
    --set-parameter cloudigrade/CLOUDIGRADE_CW_RETENTION_DAYS=${CLOUDIGRADE_CW_RETENTION_DAYS} \
    --set-parameter cloudigrade/CLOUDIGRADE_ENABLE_CLOUDWATCH=True \
    --set-parameter cloudigrade/AZURE_CLIENT_ID=${AZURE_CLIENT_ID} \
    --set-parameter cloudigrade/AZURE_CLIENT_SECRET=${AZURE_CLIENT_SECRET} \
    --set-parameter cloudigrade/AZURE_SP_OBJECT_ID=${AZURE_SP_OBJECT_ID} \
    --set-parameter cloudigrade/AZURE_SUBSCRIPTION_ID=${AZURE_SUBSCRIPTION_ID} \
    --set-parameter cloudigrade/AZURE_TENANT_ID=${AZURE_TENANT_ID} \

# Run smoke tests with ClowdJobInvocation
source $CICD_ROOT/cji_smoke_test.sh
