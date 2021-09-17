#!/bin/sh

#
# Cloudigrade-api Initialization as invoked in the Clowder initContainer.
#
export LOGPREFIX="Clowder Init:"
echo "${LOGPREFIX}"

# This is so ansible can run with a random {u,g}id in OpenShift
echo "ansible:x:$(id -u):$(id -g):,,,:${HOME}:/bin/bash" >> /etc/passwd
echo "ansible:x:$(id -G | cut -d' ' -f 2)" >> /etc/group
id

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

ANSIBLE_CONFIG=/opt/cloudigrade/playbooks/ansible.cfg ansible-playbook -e env=${CLOUDIGRADE_ENVIRONMENT} playbooks/manage-cloudigrade.yml | tee /tmp/slack-payload

if [[ -z "${SLACK_TOKEN}" ]]; then
  echo "Cloudigrade Init: SLACK_TOKEN is not defined, not uploading the slack payload"
else
  slack_payload=`cat /tmp/slack-payload | tail -n 3`
  slack_payload="${CLOUDIGRADE_ENVIRONMENT} -- $slack_payload"
  curl -X POST --data-urlencode "payload={\"channel\": \"#cloudmeter-deployments\", \"text\": \"$slack_payload\"}" ${SLACK_TOKEN}
fi

python3 ./manage.py configurequeues
python3 ./manage.py syncbucketlifecycle
python3 ./manage.py migrate
