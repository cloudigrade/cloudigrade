#!/bin/sh

# This is so ansible can run with a random {u,g}id in OpenShift
echo "ansible:x:$(id -u):$(id -g):,,,:${HOME}:/bin/bash" >> /etc/passwd
echo "ansible:x:$(id -G | cut -d' ' -f 2)" >> /etc/group
id

ANSIBLE_CONFIG=/home/cloudigrade/playbooks/ansible.cfg ansible-playbook -e env=${CLOUDIGRADE_ENVIRONMENT} playbooks/manage-cloudigrade.yml | tee slack-payload

slack_payload=`cat slack-payload | tail -n 3`
curl -X POST --data-urlencode "payload={\"channel\": \"#cloudmeter-deployments-dev\", \"text\": \"$slack_payload\"}" ${SLACK_TOKEN}

python3 ./manage.py configurequeues
python3 ./manage.py syncbucketlifecycle
python3 ./manage.py migrate
