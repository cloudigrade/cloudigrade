PYTHON	= $(shell which python)

TOPDIR  = $(shell pwd)
PYDIR	= cloudigrade

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo "  help           to show this message"
	@echo "  clean          to clean the project directory of any scratch files, bytecode, logs, etc."
	@echo "  reinitdb       to drop and recreate the database"

clean:
	git clean -fdx -e .idea/ -e *env/

reinitdb:
	rm -rf $(TOPDIR)/db.sqlite3
	$(PYTHON) $(PYDIR)/manage.py migrate --settings=config.settings.local
