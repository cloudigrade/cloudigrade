***********
cloudigrade
***********

|license| |Tests Status| |codecov|


What is cloudigrade?
====================

**cloudigrade** was an open-source suite of tools for tracking RHEL use in public cloud platforms, but in early 2023, its features were stripped-down to support only the minimum needs of other internal Red Hat services. The `1.0.0 <https://github.com/cloudigrade/cloudigrade/releases/tag/1.0.0>`_ tag marks the last fully-functional version of **cloudigrade**.

What did cloudigrade do?
------------------------

**cloudigrade** actively checked a user's account in a particular cloud for running instances, tracked when instances were powered on, determined if RHEL was installed on them, and provided the ability to generate reports to see how many cloud compute resources had been used in a given time period.

See the `cloudigrade wiki <https://github.com/cloudigrade/cloudigrade/wiki>`_ or the following documents for more details:

- `Contributing to cloudigrade <./CONTRIBUTING.rst>`_
- `cloudigrade architecture <./docs/architecture.md>`_
- `Development environment setup and commands <./docs/development-environment.rst>`_
- `REST API Examples <./docs/rest-api-examples.rst>`_


What are "Doppler" and "Cloud Meter"?
-------------------------------------

Doppler was an early code name for **cloudigrade**. Cloud Meter is a product-ized Red Hat name for its running **cloudigrade** service. ``cloudigrade == Doppler == Cloud Meter`` for all intents and purposes. 😉


.. |license| image:: https://img.shields.io/github/license/cloudigrade/cloudigrade.svg
   :target: https://github.com/cloudigrade/cloudigrade/blob/master/LICENSE
.. |Tests Status| image:: https://github.com/cloudigrade/cloudigrade/actions/workflows/tests.yml/badge.svg?branch=master
   :target: https://github.com/cloudigrade/cloudigrade/actions/workflows/tests.yml?query=branch%3Amaster
.. |codecov| image:: https://codecov.io/gh/cloudigrade/cloudigrade/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/cloudigrade/cloudigrade
