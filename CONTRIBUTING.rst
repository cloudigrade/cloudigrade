***************************
Contributing to cloudigrade
***************************

First of all, thank you for considering contributing to **cloudigrade**! 😀 The core project maintainers are developers at Red Hat, but we would also welcome additional contributions from the broader community. Please take a look at this document to see how you can best help us out.

.. contents::


Issues
======


Filing a bug
------------

If you believe you have found a bug, please `create an issue <https://github.com/cloudigrade/cloudigrade/issues/new/choose>`_ using the "Bug report" template. Please fill out the issue's description completely and include all of the following information:

- a brief summary of the bug
- steps to reproduce the problematic behavior
- expected output given a particular input
- actual undesired output given a particular input

If you believe there are tests passing that shouldn't be, please include references to them and explain why you think they may be wrong.

Bug issues on GitHub should have the ``bug`` label set.


Requesting a feature
--------------------

If you have an idea or suggestion for a new feature or change in behavior, please `create an issue <https://github.com/cloudigrade/cloudigrade/issues/new/choose>`_ using the "Feature request" template. Please fill out the issue's description completely including a proper user story summary and list of acceptance criteria. The team will then use `the GitHub project board <https://github.com/orgs/cloudigrade/projects/5>`_ to prioritize and guide development through a kanban process.

If you are unfamiliar with the concepts of user stories or kanban, please take a look at:

- `What is a user story? <https://www.mountaingoatsoftware.com/agile/user-stories>`_
- `What is kanban? <https://www.atlassian.com/agile/kanban>`_
- `When Kanban is the Better Choice <https://www.mountaingoatsoftware.com/blog/when-kanban-is-the-better-choice>`_

An issue for a feature request should be formatted as a user story with the typical "As a <type of user>, I want <some goal> so that <some reason>" description and a list of more detailed acceptance criteria that must be met before the feature should be considered complete. The more you explain about *why* you need a feature and *what* its acceptance criteria are, the more likely we will understand your needs and help complete the work.

Issues that are more investigative in nature may instead be treated as a spike and have a simplified description containing a brief explanation of the expected output. Since spikes typically just involve performing research and proposing a solution, we typically include a timebox in the description and omit the t-shirt size during backlog refinement.


Issue life cycle
----------------

Issues in `the GitHub project board <https://github.com/orgs/cloudigrade/projects/5>`_ typically go through the following steps:

- Create an issue with some basic (but perhaps incomplete) definition.
- We discuss the issue at `backlog refinement <https://www.mountaingoatsoftware.com/blog/product-backlog-refinement-grooming>`_. When we are confident we have enough information to start working, we add a `t-shirt size estimate <https://explainagile.com/blog/t-shirt-size-estimation/>`_, remove the ``needs-definition`` label if present, and add the issue to our project board.
- As a developer becomes available, they will assign themself to an issue in Backlog, move it from Backlog to In Progress, and start working on it. A developer should only move issues from the Backlog when they are actually beginning work.
- The assigned developer creates a pull request when their code changes are ready for review. The PR should include a link to the original issue, an explanation of the change, and ideally a demo of its changed behavior.
- Other developers review, give feedback, and approve (but not merge) the request.
- The developer coordinates with QE or any related parties before merging the code. The developer can then merge their PR or request a maintainer merge it if the developer does not have permission.
- Another developer or QE verifies that the issue's acceptance criteria have been met and closes the issue. This automatically moves the issue to the Done column on the board.


Coding style
============

**cloudigrade** is a `Python <https://www.python.org/>`_ `Django <https://www.djangoproject.com/>`_ project with heavy use of `Django Rest Framework <https://www.django-rest-framework.org/>`_.

We enforce consistency in the code using `Flake8 <https://pypi.org/project/flake8/>`_ with the following additional plugins enabled:

- `flake8-docstrings <https://pypi.org/pypi/flake8-docstrings>`_
- `flake8-import-order <https://pypi.org/pypi/flake8-import-order>`_
- `flake8-black <https://pypi.org/project/flake8-black/>`_

This means that all our submitted code should conform to `Black's opinionated code style <https://black.readthedocs.io/en/stable/the_black_code_style.html>`_ and more generally the `PEP 8 Style Guide for Python Code <https://www.python.org/dev/peps/pep-0008/>`_.

All code **must** cleanly pass Flake8 checks before it can be accepted. Occasional exceptions may be made to skip checks with ``# noqa`` comments, but these are strongly discouraged and must be reasonably justified.

Imports should be grouped and then sorted alphabetically following the `pycharm style <https://github.com/PyCQA/flake8-import-order#styles>`_. You may use the command-line tool `isort <https://pypi.org/project/isort/>`_ and `Black <https://github.com/psf/black>`_ to automatically clean up imports, but please manually review its changes before committing to ensure that there are no unintended side-effects. Only commit changes to imports if they are specifically relevant to other code you are changing. Example ``isort`` usage:

.. code-block:: bash

    # view diff of suggested changes
    isort -df -rc ./cloudigrade/

    # apply all changes to files
    isort -rc ./cloudigrade/

If you use PyCharm or IntelliJ IDEA with the Python plugin, you can coerce it to use a compliant import behavior by `configuring your Optimize Imports settings <docs/illustrations/pycharm-settings-imports.png>`_.

Aternatively, you may eschew PyCharm's built-in import optimizer and instead `add "isort" as an External Tool <docs/illustrations/pycharm-isort-external-tool.png>`_ and `give it a custom keyboard shortcut <docs/illustrations/pycharm-isort-keymap.png>`_.

If you use Visual Studio Code with the `ms-python.python <https://marketplace.visualstudio.com/items?itemName=ms-python.python>`_ extension enabled, its "Python Refactor: Sort Imports" action will use ``isort`` with our custom ``.isort.cfg`` automatically by default.


Database migrations
===================

Any new code that includes a change to models may require new database migrations that must be included with those model changes. You can use the Django management commands to create migration files like this:

.. code-block:: sh

    ./cloudigrade/manage.py makemigrations

We generally reject any edits to *existing* migrations because we must assume old migrations have already been applied to running databases, and any new edits to those migrations would never be applied. Editing an old migration implies that everyone running **cloudigrade** must drop its database, recreate it, and run all migrations from scratch. Although there might be some special circumstance when editing existing migrations is OK, the entire team of maintainers *must* agree and understand the consequences before accepting any such edits.

In our main deployed environments, we apply migrations during a deployment mid-hook. This means that we have _stopped_ running any instances of **cloudigrade** before starting the migration and we do not start running again until the migration is complete. This means that you don't have to worry too much about writing code that supports both old and new models at the same time, but it also means you must write your migrations in a way that will complete quickly with minimal downtime.


Contributing code
=================

**cloudigrade** code lives on `GitHub <https://github.com/cloudigrade/>`_, and all contributions should be submitted there via pull requests.


Branching strategy
------------------

**cloudigrade** follows a simplified `git flow <http://nvie.com/posts/a-successful-git-branching-model/>`_. The ``master`` branch is production-like and should either reflect the current state of the released/live running service or be ready to release at any time. All in-development work lives in other branches. We do *not* have perpetual ``develop`` or ``release`` branches. Changes are introduced to master through pull requests directly from short-lived feature branches.

Merge commits are forbidden on master. Use ``git rebase`` to keep the history lineage clean and comprehensible. We encourage you to squash commits within your branch to minimize noise. If you are uncomfortable rebasing history, you may use merge commits on your personal development branch *only if your entire branch is squashed* when it lands on master.

Ideally, commits are *atomic* in the sense that they contain everything necessary and related to a particular behavior change and provide real incremental value in isolation. Drop or squash all commits that just act as experimental "work in progress" checkpoints.

When you create a branch for your change, we *prefer* you use a short title that is prefixed by the issue number it is resolving. This allows us to quickly spot the connection at a glance without digging through links or commit messages. For example, here are the names of some previous short-lived branches:

- ``105-polymorphic-api``
- ``28-save-on-off-events``
- ``52-dockerize``


Pull requests
-------------

When you submit your pull request, include a link in the description to the issue that the code change is addressing. You should also include in either the description or a comment a link to a pre-recorded demo that shows the new behavior changes described in your merge request. We like to use `asciinema <https://asciinema.org/>`_ for demos of command-line functionality.

**cloudigrade** uses `GitHub Actions <https://docs.github.com/en/actions>`_ workflows to verify the quality of incoming code. Every pull request must successfully complete its workflow that effectively does the following:

- runs Django unit tests and reports coverage to codecov
- runs Flake8 lint checks
- verifies the ``openapi.json`` file matches the current API implementation
- verifies the ``rest-api-examples.rst`` file matches the current API behavior
- builds a Docker image and pushes it to `the GitHub container registry <https://github.com/orgs/cloudigrade/packages/container/package/cloudigrade>`_

See the ``.github/workflows/*.yml`` files for more details.

Pull requests may be merged and closed by maintainers of the **cloudigrade** org in GitHub. Generally, the same contributor who authored the change will also merge their request shortly after it has been approved by other team members.


Test coverage
-------------

All code changes should be accompanied by automated tests to cover the affected behavior and lines of code. Ideal submissions include tests to cover "happy path" cases, error cases, and known edge cases.

**cloudigrade** tests run in tox's ``py38`` environment and must pass cleanly before we can accept a pull request. The full test suite should complete in less than one minute, and because this is reasonably fast, we encourage contributors to run all tests locally during development and before submitting any changes.

We strive for very high coverage of our code by tests, and any code additions or changes that reduce our rate of coverage should be justified. codecov integration will comment on pull requests and block acceptance if coverage drops below our project thresholds.


Code reviews
------------

At least one project maintainer must review the changes before the merge request may be accepted. Reviewers may add comments and request additional changes; so, please watch for any notifications and respond accordingly.

Code reviews are a "safe place" where everyone should be willing to accept questions, feedback, and criticism. This is a place for us to learn from each other and improve the quality of the collective code. Please disassociate criticism in the reviews from your personal ego; *you are not your code*.


Running code checks and tests locally
=====================================

Once your environment is set up, simply use ``tox``:

.. code-block:: bash

    # run all tests and code quality checks
    tox

    # run only Django tests
    tox -e py38

    # run only code quality checks
    tox -e flake8
