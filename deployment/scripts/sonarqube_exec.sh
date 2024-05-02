#!/bin/bash
set -e

WORKSPACE="/workspace"
KEYSTORE_FILE="/tmp/RH-IT-Root-CA.keystore"
SONARQUBE_BIN_PATH="${WORKSPACE}/sonarqube/extract/${SONAR_SCANNER_NAME}/bin"

# Show Java's home path and version for possible debugging.
echo "JAVA_HOME=${JAVA_HOME}"
"${JAVA_HOME}"/bin/java -version

# Import the CA cert so the SonarQube scanner can communicate with the internal server.
"${JAVA_HOME}"/bin/keytool \
  -keystore "${KEYSTORE_FILE}" \
  -import \
  -alias RHIT-CA-2015 \
  -file "${WORKSPACE}/deployment/RHIT-CA-2015.crt" \
  -storepass redhat \
  -noprompt
"${JAVA_HOME}"/bin/keytool \
  -keystore "${KEYSTORE_FILE}" \
  -import \
  -alias RHIT-CA-2022 \
  -file "${WORKSPACE}/deployment/RHIT-CA-2022.crt" \
  -storepass redhat \
  -noprompt

# Move into /tmp because it's (more) reliably writable,
# and sonar-scanner needs to write some files.
SONAR_USER_HOME=/tmp/sonar
mkdir -p "${SONAR_USER_HOME}"
cd "${SONAR_USER_HOME}"

# Copy only the .git and cloudigrade directories.
# .git is required for sonar's SCM integration.
# We want to scan *only* cloudigrade's source code, not anything else.
# For example, if a virtualenv directory exists, we don't want to scan that.
cp -R "${WORKSPACE}/"{.git,cloudigrade} "${SONAR_USER_HOME}"

export SONAR_SCANNER_OPTS="-Djavax.net.ssl.trustStore=${KEYSTORE_FILE} -Djavax.net.ssl.trustStorePassword=redhat"
${SONARQUBE_BIN_PATH}/sonar-scanner \
  -Dsonar.projectKey=console.redhat.com:cloudigrade \
  -Dsonar.branch.name="${GIT_BRANCH}" \
  -Dsonar.sources="${SONAR_USER_HOME}" \
  -Dsonar.host.url="${SONARQUBE_REPORT_URL}" \
  -Dsonar.projectVersion="${COMMIT_SHORT}" \
  -Dsonar.login="${SONARQUBE_TOKEN}"
