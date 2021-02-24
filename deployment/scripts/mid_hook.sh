#!/bin/sh

echo "ansible:x:$(id -u):$(id -g):,,,:${HOME}:/bin/bash" >> /etc/passwd
echo "ansible:x:$(id -G | cut -d' ' -f 2)" >> /etc/group
id
export AWS_ACCESS_KEY_ID=${ROOT_AWS_ACCESS_KEY_ID}
export AWS_SECRET_ACCESS_KEY=${ROOT_AWS_SECRET_ACCESS_KEY}
ansible-playbook -e env=ci playbooks/manage-cloudigrade.yml
source /mnt/secret_store/.env
python3 ./manage.py configurequeues
python3 ./manage.py migrate
