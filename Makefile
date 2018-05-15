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
	@echo "  oc-up-dev                     to start the cluster and deploy supporting services for running a local cloudigrade instance against the cluster."
	@echo "  oc-up-all                     to start the cluster and deploy supporting services along with cloudigrade."
	@echo "  oc-down                       to stop the local OpenShift cluster."
	@echo "  oc-clean                      to stop the local OpenShift cluster and delete configuration."
	@echo "==[OpenShift/Deployment Shortcuts]==================================="
	@echo "  oc-create-templates           to create the ImageStream and template objects."
	@echo "  oc-create-db                  to create and deploy the DB."
	@echo "  oc-create-queue               to create and deploy the queue."
	@echo "  oc-create-cloudigrade         to create and deploy the cloudigrade."
	@echo "  oc-create-registry-route      to create a route for the internal registry."
	@echo "  oc-run-dev                    to start the local dev server allowing it to connect to supporting services running in the cluster."
	@echo "==[OpenShift/Dev Shortcuts]=========================================="
	@echo "  oc-login-admin                to log into the local cluster as an admin."
	@echo "  oc-login-developer            to log into the local cluster as a developer."
	@echo "  oc-run-migrations             to run migrations from local dev environment against the DB running in the cluster."
	@echo "  oc-user                       to create a Django super user for cloudigrade running in a local OpenShift cluster."
	@echo "  oc-user-authenticate          to generate an auth token for a user for cloudigrade running in a local OpenShift cluster."
	@echo "  oc-forward-ports              to forward ports for PostgreSQL and RabbitMQ for local development."
	@echo "  oc-stop-forwarding-ports      to stop forwarding ports for PostgreSQL and RabbitMQ for local development."
	@echo "  oc-get-registry-route         to get the registry URL."
	@echo "  oc-build-cloudigrade          to build and tag cloudigrade for the local registry."
	@echo "  oc-push-cloudigrade           to push cloudigrade to the local registry."
	@echo "  oc-build-and-push-cloudigrade to build and push cloudigrade to the local registry."

clean:
	git clean -fdx -e .idea/ -e *env/

unittest:
	$(PYTHON) $(PYDIR)/manage.py test --settings=config.settings.local account analyzer util

oc-login-admin:
	oc login -u system:admin

oc-login-developer:
	oc login -u developer -p developer --insecure-skip-tls-verify

oc-up:
	oc cluster up \
		--image=$(OC_SOURCE) \
		--version=$(OC_VERSION) \
		--host-data-dir=$(OC_DATA_DIR) \
		--use-existing-config
ifeq ($(OS),Linux)
	make oc-login-developer
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
		-p DJANGO_ALLOWED_HOSTS=* \
		-p DJANGO_DATABASE_HOST=postgresql.myproject.svc \
		-p RABBITMQ_HOST=rabbitmq.myproject.svc \
	| oc create -f -

oc-forward-ports:
	-make oc-stop-forwarding-ports 2>/dev/null
	oc port-forward $$(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=postgresql) 5432 &
	oc port-forward $$(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=rabbitmq) 5672 &

oc-stop-forwarding-ports:
	kill -HUP $$(ps -eo pid,command | grep "oc port-forward" | grep -v grep | awk '{print $$1}')

oc-up-dev: oc-up sleep-60 oc-create-templates oc-create-db oc-create-queue

oc-up-all: oc-up sleep-60 oc-create-templates oc-create-db oc-create-queue sleep-30 oc-create-cloudigrade

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
	http post localhost:8080/auth/users/create/ \
	    username=user password=password
	$(PYTHON) $(PYDIR)/manage.py drf_create_token user --settings=config.settings.local

superuser:
	-$(PYTHON) $(PYDIR)/manage.py createsuperuser \
	    --settings=config.settings.local \
	    --username=admin --email=admin@example.com --noinput
	$(PYTHON) $(PYDIR)/manage.py drf_create_token admin --settings=config.settings.local

user-authenticate:
	@read -p "User name: " uname; \
	$(PYTHON) $(PYDIR)/manage.py drf_create_token $$uname --settings=config.settings.local

oc-user:
	http post cloudigrade-myproject.127.0.0.1.nip.io/auth/users/create/ \
	    username=user password=userpassword
	oc rsh -c cloudigrade \
	    $$(oc get pods -o jsonpath='{.items[*].metadata.name}' \
	                   -l name=cloudigrade) \
	    scl enable rh-postgresql96 rh-python36 -- \
	    python manage.py drf_create_token user

oc-superuser:
	-oc rsh -c cloudigrade \
	    $$(oc get pods -o jsonpath='{.items[*].metadata.name}' \
	                   -l name=cloudigrade) \
	    scl enable rh-postgresql96 rh-python36 -- \
	    python manage.py createsuperuser \
	        --username=admin --email=admin@example.com --noinput
	oc rsh -c cloudigrade \
	    $$(oc get pods -o jsonpath='{.items[*].metadata.name}' \
	                   -l name=cloudigrade) \
	    scl enable rh-postgresql96 rh-python36 -- \
	    python manage.py drf_create_token admin

oc-user-authenticate:
	@read -p "User name: " uname; \
	oc rsh -c cloudigrade $$(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=cloudigrade) scl enable rh-postgresql96 rh-python36 -- python manage.py drf_create_token $$uname

oc-create-registry-route: oc-login-admin
	oc create route edge docker-registry --service=docker-registry -n default
	make oc-login-developer

oc-get-registry-route: oc-login-admin
	$(eval ROUTE := $(shell oc get route docker-registry --no-headers --template={{.spec.host}} -n default))
	make oc-login-developer

oc-build-cloudigrade: oc-get-registry-route
	docker build -t $(ROUTE)/myproject/cloudigrade:latest .

oc-push-cloudigrade: oc-get-registry-route
	docker login -u developer -p $$(oc whoami -t) $(ROUTE)
	docker push $(ROUTE)/myproject/cloudigrade:latest

oc-build-and-push-cloudigrade: oc-build-cloudigrade oc-push-cloudigrade

docs-seqdiag:
	cd docs && for FILE in *.diag; do seqdiag -Tsvg $$FILE; done

docs: docs-seqdiag

sleep-60:
	@echo "Allow the cluster to startup and set all internal services up."
	sleep 60

sleep-30:
	@echo "Allow the DB to start before deploying cloudigrade."
	sleep 30

.PHONY: docs
