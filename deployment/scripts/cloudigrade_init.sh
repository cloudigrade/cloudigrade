#!/bin/sh

#
# Cloudigrade-api Initialization as invoked in the Clowder initContainer.
#
export LOGPREFIX="Clowder Init:"
echo "${LOGPREFIX}"

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

if [[ -z "${ACG_CONFIG}" ]]; then
  echo "${LOGPREFIX} Not running in a clowder environment"
else
  echo "${LOGPREFIX} Running in a clowder environment"

  export DATABASE_HOST="`cat $ACG_CONFIG | jq -r '.database.hostname'`"
  export DATABASE_PORT="`cat $ACG_CONFIG | jq -r '.database.port'`"

  # Wait for the database to be ready
  echo "${LOGPREFIX} Waiting for database readiness ..."
  check_svc_status $DATABASE_HOST $DATABASE_PORT

  # If postigrade is deployed in Clowder, let's also make sure sure that it is ready
  export PG_SVC="`cat $ACG_CONFIG | jq -r '.endpoints[].app' | grep -n 'postigrade'`"
  if [[ -n "${PG_SVC}" ]]; then
    EP_NUM=$(( ${PG_SVC/:*/} - 1 ))
    DATABASE_HOST=$(cat $ACG_CONFIG | jq -r ".endpoints[${EP_NUM}].hostname")
    DATABASE_PORT=$(cat $ACG_CONFIG | jq -r ".endpoints[${EP_NUM}].port")

    echo "${LOGPREFIX} Waiting for postigrade readiness ..."
    check_svc_status $DATABASE_HOST $DATABASE_PORT
  fi
fi

python3 ./manage.py migrate
