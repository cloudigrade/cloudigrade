***********
cloudigrade
***********

|license| |Build Status| |codecov|


What is cloudigrade?
====================

**cloudigrade** is an open-source suite of tools for tracking RHEL use in public cloud platforms. **cloudigrade** actively checks a user's account in a particular cloud for running instances, tracks when instances are powered on, determines if RHEL is installed on them, and provides the ability to generate reports to see how many cloud compute resources have been used in a given time period.

See also: `Development environment setup and commands <./docs/development-environment.rst>`_


What are "Doppler" and "Cloud Meter"?
-------------------------------------

Doppler was an early code name for **cloudigrade**. Cloud Meter is a product-ized Red Hat name for its running **cloudigrade** service. ``cloudigrade == Doppler == Cloud Meter`` for all intents and purposes. 😉


.. |license| image:: https://img.shields.io/github/license/cloudigrade/cloudigrade.svg
   :target: https://github.com/cloudigrade/cloudigrade/blob/master/LICENSE
.. |Build Status| image:: https://github.com/cloudigrade/cloudigrade/actions/workflows/push.yml/badge.svg?branch=master
   :target: https://github.com/cloudigrade/cloudigrade/actions?query=branch%3Amaster
.. |codecov| image:: https://codecov.io/gh/cloudigrade/cloudigrade/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/cloudigrade/cloudigrade
