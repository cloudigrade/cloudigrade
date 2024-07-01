#!/bin/bash
set -e

# All of these *should* be set already in the environment,
# but let's offer probably-reasonable defaults to be safe.
WORKSPACE="${WORKSPACE:-${PWD}}"
SONARQUBE_REPORT_URL="${SONARQUBE_REPORT_URL:-https://sonarqube.corp.redhat.com}"
GIT_BRANCH="${GIT_BRANCH:-master}"

# Set up the environment.
RUN_DIR="${WORKSPACE}"
rm -rf "${RUN_DIR}/sonarqube"
mkdir -p "${RUN_DIR}/sonarqube/"{scripts,download,extract,certs}
cp "${RUN_DIR}/deployment/scripts/sonarqube_exec.sh" "${RUN_DIR}/sonarqube/scripts"
whoami
ls -alh ${RUN_DIR}/sonarqube/scripts
chmod +x "${RUN_DIR}/sonarqube/scripts/sonarqube_exec.sh"
COMMIT_SHORT=$(git rev-parse --short=7 HEAD)
JAVA_IMAGE="registry.access.redhat.com/ubi9/openjdk-17"
SONAR_SCANNER_OS="linux"
SONAR_SCANNER_CLI_VERSION="4.6.2.2472"
SONAR_SCANNER_DOWNLOAD_NAME="sonar-scanner-cli-${SONAR_SCANNER_CLI_VERSION-$SONAR_SCANNER_OS}.zip"
SONAR_SCANNER_NAME="sonar-scanner-${SONAR_SCANNER_CLI_VERSION-$SONAR_SCANNER_OS}"

# Copy the CA certs so the SonarQube scanner can communicate with the internal server.
cp ${WORKSPACE}/deployment/RHIT-CA-2015.crt ${RUN_DIR}/sonarqube/certs/RHIT-CA-2015.crt
cp ${WORKSPACE}/deployment/RHIT-CA-2022.crt ${RUN_DIR}/sonarqube/certs/RHIT-CA-2022.crt

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
echo GIT_BRANCH="${GIT_BRANCH}" >> "${ENV_FILE}"
echo SONARQUBE_TOKEN="${SONARQUBE_TOKEN}" >> "${ENV_FILE}"
echo SONAR_SCANNER_NAME="${SONAR_SCANNER_NAME}" >> "${ENV_FILE}"

# Run the SonarQube scanner in a Docker container.
docker pull "${JAVA_IMAGE}"
docker run \
  -v"${RUN_DIR}":/workspace \
  --env-file "${ENV_FILE}" \
  "${JAVA_IMAGE}" \
  bash /workspace/sonarqube/scripts/sonarqube_exec.sh

# The following junit-dummy.xml is needed because the pr-check job always
# checks for a junit artifact. If not present, the pr-check job will fail.
mkdir -p "${WORKSPACE}/artifacts"
cat << EOF > "${WORKSPACE}/artifacts/junit-dummy.xml"
<testsuite tests="1">
    <testcase classname="dummy" name="dummytest"/>
</testsuite>
EOF
