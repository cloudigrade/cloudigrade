PYTHON	= $(shell which python)

TOPDIR    = $(shell pwd)
PYDIR	  = $(TOPDIR)/cloudigrade

# These need to match the mount paths in docker-compose.yml
TMPDIR    = /tmp/cloudigrade
SOCKETDIR = $(TMPDIR)/socket

ifeq ($(UNAME_S),Darwin)
	FLAVOR = darwin
	SUDO = ''
else ifneq (,$(shell cat /etc/redhat-release))
	FLAVOR = redhat
	SUDO = '/usr/bin/sudo'
else ifneq (,$(shell cat /etc/debian_version))
	FLAVOR = debian
else
	FLAVOR = unknown
endif

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo "  help                     to show this message"
	@echo "  clean                    to clean the project directory of any scratch files, bytecode, logs, etc."
	@echo "  reinitdb                 to drop and recreate the database"
	@echo "  remove-compose-db        to remove the temp docker psql directory"
	@echo "  run-docker-migrations    to run migrations against docker psql"
	@echo "  unittest                 to run unittests"
	@echo "  user                     to create a Django super user"
	@echo "  user-authenticate        to generate an auth token for a user"
	@echo "  start-compose            to compose all containers in detached state"
	@echo "  stop-compose             to stop all containers"
	@echo "  start-db                 to start the psql db in detached state"

clean:
	git clean -fdx -e .idea/ -e *env/

reinitdb: stop-compose remove-compose-db start-db run-docker-migrations

remove-compose-db:
	rm -rf $(TOPDIR)/pg_data

remove-compose-queue:
	rm -rf $(TOPDIR)/rabbitmq

run-docker-migrations:
	sleep 1
	$(PYTHON) $(PYDIR)/manage.py migrate --settings=config.settings.local

unittest:
	$(PYTHON) $(PYDIR)/manage.py test --settings=config.settings.local account analyzer util

user:
	$(PYTHON) $(PYDIR)/manage.py createsuperuser --settings=config.settings.local

user-authenticate:
	@read -p "User name: " uname; \
	$(PYTHON) $(PYDIR)/manage.py drf_create_token $$uname --settings=config.settings.local

# There is a race condition with how docker applies MCS
# categories on SELinux-enabled systems. So, we need to ensure
# the app server starts up after the web proxy.
#
# Users should also set:
# setsebool -P container_connect_any on
start-compose:
	@if [ $(FLAVOR) == 'redhat' ]; then \
		docker-compose up --build -d web db queue; \
		$(SUDO) chmod 777 $(SOCKETDIR); \
		$(SUDO) chcon -l s0 $(SOCKETDIR); \
		docker-compose up --build -d app; \
	else \
		docker-compose up --build -d; \
	fi

stop-compose:
	docker-compose down
	$(SUDO) rm -rf $(TMPDIR)

start-db:
	docker-compose up -d db

start-queue:
	docker-compose up -d queue
