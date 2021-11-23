#!/bin/bash

export RUN_DIR="${PWD}"

echo "SonarQube Scan"
echo "Directory: ${RUN_DIR}"
echo "JAVA_HOME: ${JAVA_HOME}"
echo "Workspace: ${WORKSPACE}"

mkdir "${RUN_DIR}/sonarqube/"
mkdir "${RUN_DIR}/sonarqube/download/"
mkdir "${RUN_DIR}/sonarqube/extract/"
mkdir "${RUN_DIR}/sonarqube/certs/"
mkdir "${RUN_DIR}/sonarqube/store/"

curl -o "${RUN_DIR}/sonarqube/certs/RH-IT-Root-CA.crt" "${RH_IT_ROOT_CA_CERT_URL}"

"${JAVA_HOME}/bin/keytool" \
  -keystore  "${RUN_DIR}/sonarqube/store/RH-IT-Root-CA.keystore" \
  -import    \
  -alias     RH-IT-Root-CA \
  -file      "${RUN_DIR}/sonarqube/certs/RH-IT-Root-CA.crt" \
  -storepass redhat \
  -noprompt

export SONAR_SCANNER_OPTS="-Djavax.net.ssl.trustStore=${RUN_DIR}/sonarqube/store/RH-IT-Root-CA.keystore -Djavax.net.ssl.trustStorePassword=redhat"

export SONAR_SCANNER_OS="linux"
if [[ "$OSTYPE" == "darwin"* ]]; then
    export SONAR_SCANNER_OS="macosx"
fi

export SONAR_SCANNER_CLI_VERSION="4.6.2.2472"
export SONAR_SCANNER_DOWNLOAD_NAME="sonar-scanner-cli-${SONAR_SCANNER_CLI_VERSION-$SONAR_SCANNER_OS}"
export SONAR_SCANNER_NAME="sonar-scanner-${SONAR_SCANNER_CLI_VERSION-$SONAR_SCANNER_OS}"

curl -o "${RUN_DIR}/sonarqube/download/${SONAR_SCANNER_DOWNLOAD_NAME}.zip" \
  https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/${SONAR_SCANNER_DOWNLOAD_NAME}.zip

unzip -d "${RUN_DIR}/sonarqube/extract/" "${RUN_DIR}/sonarqube/download/$SONAR_SCANNER_DOWNLOAD_NAME.zip"

export PATH="${RUN_DIR}/sonarqube/extract/$SONAR_SCANNER_NAME/bin:$PATH"

COMMIT_SHORT=$(git rev-parse --short=7 HEAD)

sonar-scanner \
  -Dsonar.projectKey=console.redhat.com:cloudigrade \
  -Dsonar.sources=./cloudigrade \
  -Dsonar.host.url=https://sonarqube.corp.redhat.com \
  -Dsonar.projectVersion=$COMMIT_SHORT \
  -Dsonar.login=$SONARQUBE_TOKEN

# The following junit-dummy.xml is needed because the pr-check job always
# checks for a junit artifact. If not present, the pr-check job will fail.
mkdir -p "${WORKSPACE}/artifacts"
cat << EOF > "${WORKSPACE}/artifacts/junit-dummy.xml"
<testsuite tests="1">
    <testcase classname="dummy" name="dummytest"/>
</testsuite>
EOF
