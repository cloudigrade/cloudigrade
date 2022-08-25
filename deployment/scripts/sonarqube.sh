#!/bin/bash
set -e

# All of these *should* be set already in the environment,
# but let's offer probably-reasonable defaults to be safe.
WORKSPACE="${WORKSPACE:-${PWD}}"
RH_IT_ROOT_CA_CERT_URL="${RH_IT_ROOT_CA_CERT_URL:-https://password.corp.redhat.com/RH-IT-Root-CA.crt}"
SONARQUBE_REPORT_URL="${SONARQUBE_REPORT_URL:-https://sonarqube.corp.redhat.com}"

# Set up the environment.
RUN_DIR="${WORKSPACE}"
rm -rf "${RUN_DIR}/sonarqube"
mkdir -p "${RUN_DIR}/sonarqube/"{scripts,download,extract,certs}
cp "${RUN_DIR}/deployment/scripts/sonarqube_exec.sh" "${RUN_DIR}/sonarqube/scripts"
COMMIT_SHORT=$(git rev-parse --short=7 HEAD)
JAVA11_IMAGE="registry.access.redhat.com/openjdk/openjdk-11-rhel7:1.12-1.1658422675"
SONAR_SCANNER_OS="linux"
SONAR_SCANNER_CLI_VERSION="4.6.2.2472"
SONAR_SCANNER_DOWNLOAD_NAME="sonar-scanner-cli-${SONAR_SCANNER_CLI_VERSION-$SONAR_SCANNER_OS}.zip"
SONAR_SCANNER_NAME="sonar-scanner-${SONAR_SCANNER_CLI_VERSION-$SONAR_SCANNER_OS}"

# Fetch the CA cert so the SonarQube scanner can communicate with the internal server.
curl --silent --show-error \
  -o "${RUN_DIR}/sonarqube/certs/RH-IT-Root-CA.crt" \
  "${RH_IT_ROOT_CA_CERT_URL}"

# Fetch and expand the SonarQube binaries.
curl --silent --show-error \
  -o "${RUN_DIR}/sonarqube/download/${SONAR_SCANNER_DOWNLOAD_NAME}" \
  "https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/${SONAR_SCANNER_DOWNLOAD_NAME}"
unzip \
  -d "${RUN_DIR}/sonarqube/extract/" \
  "${RUN_DIR}/sonarqube/download/${SONAR_SCANNER_DOWNLOAD_NAME}"

# Create an env file for the SonarQube scanner.
ENV_FILE="${RUN_DIR}/sonarqube/sonarqube.env"
echo SONARQUBE_REPORT_URL="${SONARQUBE_REPORT_URL}" > "${ENV_FILE}"
echo COMMIT_SHORT="${COMMIT_SHORT}" >> "${ENV_FILE}"
echo SONARQUBE_TOKEN="${SONARQUBE_TOKEN}" >> "${ENV_FILE}"
echo SONAR_SCANNER_NAME="${SONAR_SCANNER_NAME}" >> "${ENV_FILE}"

# Run the SonarQube scanner in a Docker container.
docker pull "${JAVA11_IMAGE}"
docker run \
  -v"${RUN_DIR}":/workspace \
  --env-file "${ENV_FILE}" \
  "${JAVA11_IMAGE}" \
  bash /workspace/sonarqube/scripts/sonarqube_exec.sh

# The following junit-dummy.xml is needed because the pr-check job always
# checks for a junit artifact. If not present, the pr-check job will fail.
mkdir -p "${WORKSPACE}/artifacts"
cat << EOF > "${WORKSPACE}/artifacts/junit-dummy.xml"
<testsuite tests="1">
    <testcase classname="dummy" name="dummytest"/>
</testsuite>
EOF
