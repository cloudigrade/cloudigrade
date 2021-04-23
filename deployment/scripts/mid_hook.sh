#!/bin/sh

# This is so ansible can run with a random {u,g}id in OpenShift
echo "ansible:x:$(id -u):$(id -g):,,,:${HOME}:/bin/bash" >> /etc/passwd
echo "ansible:x:$(id -G | cut -d' ' -f 2)" >> /etc/group
id

ANSIBLE_CONFIG=/opt/cloudigrade/playbooks/ansible.cfg ansible-playbook -e env=${CLOUDIGRADE_ENVIRONMENT} playbooks/manage-cloudigrade.yml | tee -a /tmp/slack-payload

slack_payload=`cat /tmp/slack-payload | tail -n 3`
slack_payload="${CLOUDIGRADE_ENVIRONMENT} -- $slack_payload"
curl -X POST --data-urlencode "payload={\"channel\": \"#cloudmeter-deployments\", \"text\": \"$slack_payload\"}" ${SLACK_TOKEN}

python3 ./manage.py configurequeues
python3 ./manage.py syncbucketlifecycle
python3 ./manage.py migrate
