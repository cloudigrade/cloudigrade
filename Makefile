PYTHON	= $(shell which python)

TOPDIR  = $(shell pwd)
PYDIR	= cloudigrade

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo "  help                     to show this message"
	@echo "  clean                    to clean the project directory of any scratch files, bytecode, logs, etc."
	@echo "  reinitdb                 to drop and recreate the database"
	@echo "  remove-compose-db        to remove the temp docker psql directory"
	@echo "  run-docker-migrations    to run migrations against docker psql"
	@echo "  unittest                 to run unittests"
	@echo "  start-compose            to compose all containers in detached state"
	@echo "  stop-compose             to stop all containers"
	@echo "  start-db                 to start the psql db in detached state"

clean:
	git clean -fdx -e .idea/ -e *env/

reinitdb: stop-compose remove-compose-db start-db run-docker-migrations

remove-compose-db:
	rm -rf $(TOPDIR)/pg_data

run-docker-migrations:
	sleep 1
	$(PYTHON) $(PYDIR)/manage.py migrate --settings=config.settings.local

unittest:
	$(PYTHON) $(PYDIR)/manage.py test --settings=config.settings.local account analyzer util

start-compose:
	docker-compose up --build -d

stop-compose:
	docker-compose down

start-db:
	docker-compose up -d db
