#!/bin/bash

set -euxo pipefail

IMAGE_NAME="quay.io/cloudservices/cloudigrade"
IMAGE_TAG=$(git rev-parse --short=7 HEAD)
DOCKER_CONF="${PWD}/.docker"

if [[ -z "$QUAY_USER" || -z "$QUAY_TOKEN" ]]; then
    echo "QUAY_USER and QUAY_TOKEN must be set"
    exit 1
fi

if [[ -z "$RH_REGISTRY_USER" || -z "$RH_REGISTRY_TOKEN" ]]; then
    echo "RH_REGISTRY_USER and RH_REGISTRY_TOKEN  must be set"
    exit 1
fi

mkdir -p "${DOCKER_CONF}"

# Log into the registries
docker --config="${DOCKER_CONF}" login -u="${QUAY_USER}" -p="${QUAY_TOKEN}" quay.io
docker --config="${DOCKER_CONF}" login -u="$RH_REGISTRY_USER" -p="$RH_REGISTRY_TOKEN" registry.redhat.io
# Pull 'Latest' Image
docker --config="${DOCKER_CONF}" pull ${IMAGE_NAME}:latest || true
# Build and Tag
docker --config="${DOCKER_CONF}" build --tag ${IMAGE_NAME}:${IMAGE_TAG} .
docker --config="${DOCKER_CONF}" tag "${IMAGE_NAME}:${IMAGE_TAG}" "${IMAGE_NAME}:latest"
# Push images
docker --config="${DOCKER_CONF}" push "${IMAGE_NAME}:latest"
docker --config="${DOCKER_CONF}" push "${IMAGE_NAME}:${IMAGE_TAG}"
