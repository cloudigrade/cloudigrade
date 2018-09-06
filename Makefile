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
	@echo "==[OpenShift/Dev Shortcuts]=========================================="
	@echo "  oc-run-dev                    to start the local dev server allowing it to connect to supporting services running in the cluster."
	@echo "  oc-run-migrations             to run migrations from local dev environment against the DB running in the cluster."
	@echo "  oc-forward-ports              to forward ports for PostgreSQL for local development."
	@echo "  oc-stop-forwarding-ports      to stop forwarding ports for PostgreSQL for local development."

clean:
	git clean -fdx -e .idea/ -e *env/

unittest:
	$(PYTHON) $(PYDIR)/manage.py test --settings=config.settings.local account analyzer util

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

user:
	$(PYTHON) $(PYDIR)/manage.py createsuperuser --settings=config.settings.local

user-authenticate:
	@read -p "User name: " uname; \
	$(PYTHON) $(PYDIR)/manage.py drf_create_token $$uname --settings=config.settings.local

docs-seqdiag:
	cd docs/illustrations && for FILE in *.diag; do seqdiag -Tsvg $$FILE; done

docs: docs-seqdiag

.PHONY: docs
