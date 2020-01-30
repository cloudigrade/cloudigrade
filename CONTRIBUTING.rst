***************************
Contributing to cloudigrade
***************************

First of all, thank you for considering contributing to **cloudigrade**! 😀 The project maintainers are developers at Red Hat, but we'd welcome additional contributions from the broader community. Please take a look at this document to see how you can best help us out.

.. contents::


Issues
======


Filing a bug
------------

If you believe you have found a bug, please create an issue using the Bug issue template. Please fill out the issue's description completely and include all of the following information:

- a brief summary of the bug
- steps to reproduce the problematic behavior
- expected output given a particular input
- actual undesired output given a particular input

If you believe there are tests passing that shouldn't be, please include references to them and explain why you think they may be wrong.

Bug issues on GitLab should have the ``bug`` label set.


Requesting a feature
--------------------

We use `the cloudigrade issue board in GitLab <https://gitlab.com/groups/cloudigrade/-/boards/603180>`_ to guide development through a scrum process. We use a custom "User Story" issue template for treating *feature requests* as *user stories* in scrum.

If you are unfamiliar with the concepts of user stories or scrum, please take a look at:

- `What is a user story? <https://www.mountaingoatsoftware.com/agile/user-stories>`_
- `What is scrum? <https://www.mountaingoatsoftware.com/agile/scrum>`_

In GitLab's issue tracker, an issue for a user story should have the ``story`` label set and follow the "User Story" template that includes the typical "As a <type of user>, I want <some goal> so that <some reason>" description with a list of more detailed acceptance criteria that must be met before the feature should be considered complete. The more you explain about *why* you need a feature and *what* its acceptance criteria are, the more likely we will understand your needs and help complete the work.

Issues that are more investigative in nature may instead set the ``spike`` label and have a simplified description containing a brief explanation of the expected output. Since spikes typically just involve performing research and proposing a solution, we typically include a timebox in the description and omit story points during backlog refinement.


Issue life cycle in scrum
-------------------------

On `the cloudigrade issue board in GitLab <https://gitlab.com/groups/cloudigrade/-/boards/603180>`_, an issue typically goes through the following steps:

- Create an issue with some basic (but perhaps incomplete) definition and set the ``needs definition`` label. The issue then appears in the **Open** column of the issue board.
- We discuss the issue at `backlog refinement <https://www.mountaingoatsoftware.com/blog/product-backlog-refinement-grooming>`_, and when we are confident we have enough information to start working, we add a `story point estimate <https://www.mountaingoatsoftware.com/blog/what-are-story-points>`_ and remove the ``needs definition`` label.
- During `sprint planning <https://www.mountaingoatsoftware.com/agile/scrum/meetings/sprint-planning-meeting>`_, if the issue is sufficiently high in priority and we have capacity to commit to it, we move the issue to **to-do** (or set the ``to-do`` label) and indicates that we expect to complete the work in the new sprint. We assigned the issue to the **milestone** for the new sprint.
- A developer moves the issue to **in-progress** (or sets the ``in-progress`` label) when work starts on it.
- The developer creates a merge request when code changes are ready for review. Other developers review, give feedback, and approve (but not merge) the request.
- QE and stakeholders verify the acceptance criteria of the issue, adding automated tests as necessary. Once the AC have been verified and marked appropriately in the issue, QE merges the branches and closes the issue.
- Celebrate as the changes go live! 🎉


Coding style
============

**cloudigrade** is a Python Django project and officially supports only Python 3.7.

We enforce consistency in the code using `Flake8 <https://pypi.org/project/flake8/>`_ with the following additional plugins enabled:

- `flake8-docstrings <https://pypi.org/pypi/flake8-docstrings>`_
- `flake8-import-order <https://pypi.org/pypi/flake8-import-order>`_
- `flake8-black <https://pypi.org/project/flake8-black/>`_

This means that all our submitted code conforms to `PEP 8 <https://www.python.org/dev/peps/pep-0008/>`_ standards and `Black's opinionated code style <https://black.readthedocs.io/en/stable/the_black_code_style.html>`_.

All code **must** cleanly pass Flake8 checks before it can be accepted. Occasional exceptions may be made to skip checks with ``# noqa`` comments, but these are strongly discouraged and must be reasonably justified.

Imports should be grouped and then sorted alphabetically following the `pycharm style <https://github.com/PyCQA/flake8-import-order#styles>`_. You may use the command-line tool `isort <https://pypi.org/project/isort/>`_ to automatically clean up imports, but please manually review its changes before committing to ensure that there are no unintended side-effects. Only commit changes to imports if they are specifically relevant to other code you are changing. Example ``isort`` usage:

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


Contributing code
=================

**cloudigrade** code lives on `GitLab <https://gitlab.com/cloudigrade/>`_, and all contributions should be submitted there via merge requests.


Branching strategy
------------------

**cloudigrade** follows a simplified `git flow <http://nvie.com/posts/a-successful-git-branching-model/>`_. The ``master`` branch is production-like and reflects the state of the released/live running service at any time (thanks to continuous deployment). All in-development work lives in other branches. We do *not* have perpetual ``develop`` or ``release`` branches. Changes are introduced to master through merge requests directly from short-lived feature branches.

Merge commits are not allowed on master. You must use rebase to keep the history lineage clean and comprehensible, and we encourage you to squash commits within your branch to minimize noise. If you are uncomfortable rebasing history, you may use merge commits on your personal development branch as long as your entire branch is squashed when it lands on master.

Ideally, commits are *atomic* in the sense that they contain everything necessary and related to a particular behavior change. Drop or squash all commits that just act as "work in progress" checkpoints.

When you create a branch for your change, we *prefer* you use a short title that is prefixed by the GitLab issue number it is resolving. This allows us to quickly spot the connection without digging through links or commit messages. For example, here are the names of some previous short-lived branches:

- ``105-polymorphic-api``
- ``28-save-on-off-events``
- ``52-dockerize``


Merge requests
--------------

When you submit your merge request, include a link in the description to the issue that the code change is addressing. You should also include in either the description or a comment a link to a pre-recorded demo that shows the new behavior changes described in your merge request.

**cloudigrade** uses `GitLab CI/CD <https://docs.gitlab.com/ee/ci/>`_ pipelines to verify the quality of incoming code. Every merge request must successfully complete jobs that effectively include:

- running Flake8 lint checks
- executing Django unit tests
- checking that the openapi.spec file matches the current API implementation
- checking code coverage of the unit tests
- building a Docker image and pushing it to `the GitLab container registry <https://gitlab.com/cloudigrade/cloudigrade/container_registry>`_
- deploying to a review environment

See the ``.gitlab-ci.yml`` file for more details.

Merge requests may be merged and closed by members of the **cloudigrade** group in GitLab. Generally, the same contributor who authored the change will merge their request shortly after the request is approved by other team members.


Test coverage
-------------

All code changes should be accompanied by automated tests to cover the affected behavior and lines of code. Ideal submissions include tests to cover "happy path" cases, error cases, and known edge cases.

**cloudigrade** tests run in tox's ``py37`` environment and must pass cleanly before we can accept a merge request. The full test suite should take on the order of seconds to complete, and because the tests are reasonably fast, we encourage contributors to run all tests locally before submitting any changes.

We strive for very high coverage of our code by tests, and any code additions or changes that reduce our rate of coverage should be justified. codecov integration will comment on merge requests and halt the process if coverage drops below our project thresholds.


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

    # run only tests for Python 3.7
    tox -e py37

    # run only code quality checks
    tox -e flake8
