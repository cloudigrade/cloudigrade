PYTHON		= $(shell which python)
PYDIR		= cloudigrade

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo "==[Local Dev]========================================================"
	@echo "  help                          to show this message."
	@echo "  clean                         to clean the project directory of any scratch files, bytecode, logs, etc."
	@echo "  unittest                      to run unittests."
	@echo "  docs                          to build all documentation."
	@echo "  docs-api-examples             to regenerate API examples .rst file."
	@echo "  docs-api-examples-test        to verify the API examples .rst file is current."
	@echo "  openapi                       to regenerate the openapi.json file at the root of the repo."
	@echo "  openapi-test                  to verify that the openapi.json file at root of the repo is current."
	@echo "  user                          to create a Django super user."

clean:
	git clean -fdx -e .idea/ -e *env/

unittest:
	$(PYTHON) $(PYDIR)/manage.py test --settings=config.settings.local account analyzer util

user:
	$(PYTHON) $(PYDIR)/manage.py createsuperuser --settings=config.settings.local

docs-api-examples:
	PYTHONPATH=cloudigrade $(PYTHON) ./docs/rest-api-examples.py > ./docs/rest-api-examples.rst

docs-api-examples-test:
	PYTHONPATH=cloudigrade $(PYTHON) ./docs/rest-api-examples.py | diff ./docs/rest-api-examples.rst -

docs: docs-api-examples

openapi:
	CLOUDIGRADE_ENVIRONMENT="make-openapi" AWS_ACCESS_KEY_ID="fake" AWS_SECRET_ACCESS_KEY="fake" $(PYTHON) $(PYDIR)/manage.py generateschema --title "Cloudigrade public API v2" --format openapi-json --settings=config.settings.test --urlconf api.urls > ./openapi.json
	CLOUDIGRADE_ENVIRONMENT="make-openapi" AWS_ACCESS_KEY_ID="fake" AWS_SECRET_ACCESS_KEY="fake" $(PYTHON) $(PYDIR)/manage.py generateschema --title "Cloudigrade internal API" --format openapi-json --settings=config.settings.test --urlconf internal.urls --url /internal/ > ./openapi-internal.json

openapi-test:
	CLOUDIGRADE_ENVIRONMENT="make-openapi-test" AWS_ACCESS_KEY_ID="fake" AWS_SECRET_ACCESS_KEY="fake" $(PYTHON) $(PYDIR)/manage.py generateschema --title "Cloudigrade public API v2" --format openapi-json --settings=config.settings.test --urlconf api.urls | diff ./openapi.json -
	CLOUDIGRADE_ENVIRONMENT="make-openapi-test" AWS_ACCESS_KEY_ID="fake" AWS_SECRET_ACCESS_KEY="fake" $(PYTHON) $(PYDIR)/manage.py generateschema --title "Cloudigrade internal API" --format openapi-json --settings=config.settings.test --urlconf internal.urls --url /internal/ | diff ./openapi-internal.json -

.PHONY: docs
