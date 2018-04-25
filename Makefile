PYTHON		= $(shell which python)

TOPDIR		= $(shell pwd)
PYDIR		= cloudigrade

OC_SOURCE	= registry.access.redhat.com/openshift3/ose
OC_VERSION	= v3.7.23
OC_DATA_DIR	= ${HOME}/.oc/openshift.local.data

OS := $(shell uname)
ifeq ($(OS),Darwin)
	PREFIX	=
else
	PREFIX	= sudo
endif

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo "  help                     to show this message"
	@echo "  clean                    to clean the project directory of any scratch files, bytecode, logs, etc."
	@echo "  unittest                 to run unittests"
	@echo "	 oc-up                    to start the local OpenShift cluster."
	@echo "	 oc-create-templates      to create the ImageStream and template objects."
	@echo "	 oc-create-db             to create and deploy the DB."
	@echo "	 oc-create-queue          to create and deploy the queue."
	@echo "	 oc-create-cloudigrade    to create and deploy the cloudigrade."
	@echo "	 oc-forward-ports         to forward ports for PostgreSQL and RabbitMQ for local development."
	@echo "	 oc-stop-forwarding-ports to stop forwarding ports for PostgreSQL and RabbitMQ for local development."
	@echo "	 oc-up-dev                to start the cluster and deploy supporting services for running a local cloudigrade instance against the cluster."
	@echo "	 oc-up-all                to start the cluster and deploy supporting services along with cloudigrade."
	@echo "	 oc-run-migrations        to run migrations from local dev environment against the DB running in the cluster."
	@echo "	 oc-run-dev               to start the local dev server allowing it to connect to supporting services running in the cluster."
	@echo "	 oc-down                  to stop the local OpenShift cluster."
	@echo "	 oc-clean                 to stop the local OpenShift cluster and delete configuration."
	@echo "  user                     to create a Django super user"
	@echo "  user-authenticate        to generate an auth token for a user"
	@echo "  docs                     to build all documentation"
	@echo "  docs-seqdiag             to regenerate docs .svg files from .diag files"

clean:
	git clean -fdx -e .idea/ -e *env/

unittest:
	$(PYTHON) $(PYDIR)/manage.py test --settings=config.settings.local account analyzer util

oc-up:
	$(PREFIX) oc cluster up \
		--image=$(OC_SOURCE) \
		--version=$(OC_VERSION) \
		--host-data-dir=$(OC_DATA_DIR) \
		--use-existing-config
ifeq ($(OS),Linux)
	oc login -u developer -p developer --insecure-skip-tls-verify
endif

oc-create-templates:
	oc create istag postgresql:9.6 --from-image=centos/postgresql-96-centos7
	oc create -f deployment/ocp/rabbitmq.yml
	oc create -f deployment/ocp/cloudigrade.yml

oc-create-db:
	oc process openshift//postgresql-persistent \
		-p NAMESPACE=myproject \
		-p POSTGRESQL_USER=postgres \
		-p POSTGRESQL_PASSWORD=postgres \
		-p POSTGRESQL_DATABASE=postgres \
		-p POSTGRESQL_VERSION=9.6 \
	| oc create -f -

oc-create-queue:
	oc process rabbitmq-persistent-template \
		-p USERNAME=guest \
		-p PASSWORD=guest \
	| oc create -f -

oc-create-cloudigrade:
	oc process cloudigrade-persistent-template \
		-p NAMESPACE=myproject \
		-p AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
		-p AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY} \
		-p NGINX_REPO_CONTEXT_DIR=docker \
		-p DJANGO_ALLOWED_HOSTS=* \
		-p DJANGO_DATABASE_HOST=postgresql.myproject.svc \
		-p RABBITMQ_HOST=rabbitmq-persistent.myproject.svc \
	| oc create -f -

oc-forward-ports:
	oc port-forward $$(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=postgresql) 5432 &
	oc port-forward $$(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=rabbitmq) 5672 &

oc-stop-forwarding-ports:
	kill -HUP $$(ps -eo pid,command | grep "oc port-forward" | grep -v grep | awk '{print $$1}')

oc-up-dev: oc-up oc-create-templates oc-create-db oc-create-queue

oc-up-all: oc-up oc-create-templates oc-create-db oc-create-queue oc-create-cloudigrade

oc-run-migrations: oc-forward-ports
	DJANGO_SETTINGS_MODULE=config.settings.local python cloudigrade/manage.py migrate
	make oc-stop-forwarding-ports

oc-run-dev: oc-forward-ports
	DJANGO_SETTINGS_MODULE=config.settings.local python cloudigrade/manage.py runserver
	make oc-stop-forwarding-ports

oc-down:
	$(PREFIX) oc cluster down

oc-clean: oc-down
	$(PREFIX) rm -rf $(OC_DATA_DIR)

user:
	$(PYTHON) $(PYDIR)/manage.py createsuperuser --settings=config.settings.local

user-authenticate:
	@read -p "User name: " uname; \
	$(PYTHON) $(PYDIR)/manage.py drf_create_token $$uname --settings=config.settings.local

docs-seqdiag:
	cd docs && for FILE in *.diag; do seqdiag -Tsvg $$FILE; done

docs: docs-seqdiag

.PHONY: docs
