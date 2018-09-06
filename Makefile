PYTHON		= $(shell which python)

TOPDIR		= $(shell pwd)
PYDIR		= cloudigrade

OC_SOURCE	= registry.access.redhat.com/openshift3/ose
OC_VERSION	= v3.9.41
OC_DATA_DIR	= ${HOME}/.oc/openshift.local.data
OC_IS_OS	= rhel7

OS := $(shell uname)
ifeq ($(OS),Darwin)
	PREFIX	=
else
	PREFIX	= sudo
endif

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo "==[Local Dev]========================================================"
	@echo "  help                          to show this message."
	@echo "  clean                         to clean the project directory of any scratch files, bytecode, logs, etc."
	@echo "  unittest                      to run unittests."
	@echo "  docs                          to build all documentation."
	@echo "  docs-seqdiag                  to regenerate docs .svg files from .diag files."
	@echo "  user                          to create a Django super user."
	@echo "  user-authenticate             to generate an auth token for a user."
	@echo "==[OpenShift]========================================================"
	@echo "==[OpenShift/Administration]========================================="
	@echo "  oc-up                         to start the local OpenShift cluster."
	@echo "  oc-up-dev                     to start the local OpenShift cluster and deploy the db."
	@echo "  oc-check-cluster              to check the cluster status."
	@echo "  oc-down                       to stop the local OpenShift cluster."
	@echo "  oc-clean                      to stop the local OpenShift cluster and delete configuration."
	@echo "==[OpenShift/Dev Shortcuts]=========================================="
	@echo "  oc-run-dev                    to start the local dev server allowing it to connect to supporting services running in the cluster."
	@echo "  oc-run-migrations             to run migrations from local dev environment against the DB running in the cluster."
	@echo "  oc-login-admin                to log into the local cluster as an admin."
	@echo "  oc-login-developer            to log into the local cluster as a developer."
	@echo "  oc-user                       to create a Django super user for cloudigrade running in a local OpenShift cluster."
	@echo "  oc-user-authenticate          to generate an auth token for a user for cloudigrade running in a local OpenShift cluster."
	@echo "  oc-forward-ports              to forward ports for PostgreSQL for local development."
	@echo "  oc-stop-forwarding-ports      to stop forwarding ports for PostgreSQL for local development."

clean:
	git clean -fdx -e .idea/ -e *env/

unittest:
	$(PYTHON) $(PYDIR)/manage.py test --settings=config.settings.local account analyzer util

oc-login-admin:
	oc login -u system:admin

oc-login-developer:
	oc login -u developer -p developer --insecure-skip-tls-verify

oc-deploy-db:
	oc process openshift//postgresql-persistent \
		-p NAMESPACE=openshift \
		-p POSTGRESQL_USER=postgres \
		-p POSTGRESQL_PASSWORD=postgres \
		-p POSTGRESQL_DATABASE=postgres \
		-p POSTGRESQL_VERSION=9.6 \
	| oc create -f -
	oc rollout status dc/postgresql

oc-up:
	oc cluster up \
		--image=$(OC_SOURCE) \
		--version=$(OC_VERSION) \
		--image-streams=$(OC_IS_OS) \
		--host-data-dir=$(OC_DATA_DIR) \
		--use-existing-config
ifeq ($(OS),Linux)
	make oc-login-developer
endif

oc-up-dev: oc-up oc-check-cluster oc-deploy-db

oc-forward-ports:
	-make oc-stop-forwarding-ports 2>/dev/null
	oc port-forward $$(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=postgresql) 5432 &

oc-stop-forwarding-ports:
	kill -HUP $$(ps -eo pid,command | grep "oc port-forward" | grep -v grep | awk '{print $$1}')

oc-run-migrations: oc-forward-ports
	DJANGO_SETTINGS_MODULE=config.settings.local python cloudigrade/manage.py migrate
	make oc-stop-forwarding-ports

oc-run-dev: oc-forward-ports
	DJANGO_SETTINGS_MODULE=config.settings.local python cloudigrade/manage.py runserver
	make oc-stop-forwarding-ports

oc-down:
	oc cluster down

oc-clean: oc-down
	$(PREFIX) rm -rf $(OC_DATA_DIR)

user:
	$(PYTHON) $(PYDIR)/manage.py createsuperuser --settings=config.settings.local

user-authenticate:
	@read -p "User name: " uname; \
	$(PYTHON) $(PYDIR)/manage.py drf_create_token $$uname --settings=config.settings.local

oc-user:
	oc rsh -c cloudigrade-api $$(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=cloudigrade-api | awk '{print $$1}') scl enable rh-python36 -- python manage.py createsuperuser

oc-user-authenticate:
	@read -p "User name: " uname; \
	oc rsh -c cloudigrade-api $$(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=cloudigrade-api | awk '{print $$1}') scl enable rh-python36 -- python manage.py drf_create_token $$uname

docs-seqdiag:
	cd docs/illustrations && for FILE in *.diag; do seqdiag -Tsvg $$FILE; done

docs: docs-seqdiag

oc-check-cluster:
	while true; do oc cluster status > /dev/null; if [ $$? == "0" ]; then echo "Cluster is up!"; break; fi; echo "Waiting for cluster to start up..."; sleep 5; done;

.PHONY: docs
