#!/bin/sh

#
# Cloudigrade-api Initialization as invoked in the Clowder initContainer.
#
export LOGPREFIX="Clowder Init:"
echo "${LOGPREFIX}"

if [[ -z "${ACG_CONFIG}" ]]; then
  echo "${LOGPREFIX} Not running in a clowder environment, exiting initialization"
  exit 1
fi

function check_svc_status() {
  local SVC_NAME=$1 SVC_PORT=$2

  [[ $# -lt 2 ]] && echo "Error: Usage: check_svc_status svc_name svc_port" && exit 1

  while true; do
    echo "${LOGPREFIX} Checking ${SVC_NAME}:$SVC_PORT status ..."
    ncat ${SVC_NAME} ${SVC_PORT} < /dev/null && break
    sleep 5
  done
  echo "${LOGPREFIX} ${SVC_NAME}:${SVC_PORT} - accepting connections"
}

export DATABASE_HOST="`cat $ACG_CONFIG | jq -r '.database.hostname'`"
export DATABASE_PORT="`cat $ACG_CONFIG | jq -r '.database.port'`"

# Wait for the database to be ready
echo "${LOGPREFIX} Waiting for database readiness ..."
check_svc_status $DATABASE_HOST $DATABASE_PORT

echo "${LOGPREFIX} Migrating the database ..."
python3 ./manage.py migrate

