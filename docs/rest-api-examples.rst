REST API Example Usage
======================

This document summarizes some examples of the cloudigrade REST API.

Examples here use the ``http`` command from
`httpie <https://httpie.org/>`_. If you want to follow along with these
exact commands, you may need to ``brew install httpie`` or
``pip install httpie`` first.

These examples also assume you are running cloudigrade on
``localhost:8080`` either via ``docker-compose`` or Django’s built-in
``runserver`` command and that you have correctly configured
cloudigrade’s environment with appropriate variables to allow it to talk
to the various clouds (e.g. ``AWS_ACCESS_KEY_ID``).

Authorization
-------------

As mentioned in `README.md <../README.md>`_, all API calls require an
``Authorization`` header. For convenience, these examples assume you
have an environment variable set like this with an appropriate token
value:

.. code:: bash

    AUTH=Authorization:"Token d1fa223f753e45dd8e311cf84ee2635b0fae5bd8"

Overview
--------

The following resource paths are currently available:

-  ``/api/v1/account/`` returns account data
-  ``/api/v1/report/`` returns usage report data

Customer Account Setup
----------------------

Create an AWS account
~~~~~~~~~~~~~~~~~~~~~

This request may take a few seconds because of multiple round-trip calls
to the AWS APIs for each region.

Request:

.. code:: bash

    http post localhost:8080/api/v1/account/ "${AUTH}" \
        resourcetype="AwsAccount" \
        account_arn="arn:aws:iam::518028203513:role/grant_cloudi_to_372779871274"

Response:

::

    HTTP/1.1 201 Created
    Allow: GET, POST, HEAD, OPTIONS
    Connection: keep-alive
    Content-Length: 278
    Content-Type: application/json
    Date: Mon, 19 Mar 2018 20:26:10 GMT
    Location: http://localhost:8080/api/v1/account/1/
    Server: nginx/1.13.9
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::518028203513:role/grant_cloudi_to_372779871274",
        "aws_account_id": "518028203513",
        "created_at": "2018-03-19T20:26:10.798690Z",
        "id": 1,
        "resourcetype": "AwsAccount",
        "updated_at": "2018-03-19T20:26:10.798727Z",
        "url": "http://localhost:8080/api/v1/account/1/"
    }

If you attempt to create an AWS account for an ARN that is already in
the system, you should get a 400 error.

Request:

.. code:: bash

    http post localhost:8080/api/v1/account/ "${AUTH}" \
        resourcetype="AwsAccount" \
        account_arn="arn:aws:iam::518028203513:role/grant_cloudi_to_372779871274"

Response:

::

    HTTP/1.1 400 Bad Request
    Allow: GET, POST, HEAD, OPTIONS
    Connection: keep-alive
    Content-Length: 69
    Content-Type: application/json
    Date: Mon, 19 Mar 2018 20:28:31 GMT
    Server: nginx/1.13.9
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": [
            "aws account with this account arn already exists."
        ]
    }

Customer Account Info
---------------------

List all accounts
~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/account/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, POST, HEAD, OPTIONS
    Connection: keep-alive
    Content-Length: 330
    Content-Type: application/json
    Date: Mon, 19 Mar 2018 20:28:48 GMT
    Server: nginx/1.13.9
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 1,
        "next": null,
        "previous": null,
        "results": [
            {
                "account_arn": "arn:aws:iam::518028203513:role/grant_cloudi_to_372779871274",
                "aws_account_id": "518028203513",
                "created_at": "2018-03-19T20:26:10.798690Z",
                "id": 1,
                "resourcetype": "AwsAccount",
                "updated_at": "2018-03-19T20:26:10.798727Z",
                "url": "http://localhost:8080/api/v1/account/1/"
            }
        ]
    }

Retrieve a specific account
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/account/1/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Connection: keep-alive
    Content-Length: 278
    Content-Type: application/json
    Date: Mon, 19 Mar 2018 20:29:39 GMT
    Server: nginx/1.13.9
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::518028203513:role/grant_cloudi_to_372779871274",
        "aws_account_id": "518028203513",
        "created_at": "2018-03-19T20:26:10.798690Z",
        "id": 1,
        "resourcetype": "AwsAccount",
        "updated_at": "2018-03-19T20:26:10.798727Z",
        "url": "http://localhost:8080/api/v1/account/1/"
    }

Usage Reporting
---------------

Retrieve a usage report
~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/report/ "${AUTH}" \
        cloud_provider=="aws" \
        cloud_account_id=="518028203513" \
        start=="2018-03-01T00:00:00" \
        end=="2018-04-01T00:00:00"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Connection: keep-alive
    Content-Length: 52
    Content-Type: application/json
    Date: Mon, 19 Mar 2018 20:29:54 GMT
    Server: nginx/1.13.9
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "aws-ami-09648c5666e4f95c7-t2.nano": 1049629.191022
    }

If you attempt to retrieve a report for an invalid cloud provider, you
should get a 400 error.

Request:

.. code:: bash

    http localhost:8080/api/v1/report/ "${AUTH}" \
        cloud_provider=="foobar" \
        cloud_account_id=="518028203513" \
        start=="2018-03-01T00:00:00" \
        end=="2018-04-01T00:00:00"

Response:

::

    HTTP/1.1 400 Bad Request
    Allow: GET, HEAD, OPTIONS
    Connection: keep-alive
    Content-Length: 56
    Content-Type: application/json
    Date: Mon, 19 Mar 2018 20:30:16 GMT
    Server: nginx/1.13.9
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "cloud_provider": [
            "\"foobar\" is not a valid choice."
        ]
    }

If you attempt to retrieve a report for an account that does not exist,
you should get a 404 error.

Request:

.. code:: bash

    http localhost:8080/api/v1/report/ "${AUTH}" \
        cloud_provider=="aws" \
        cloud_account_id=="1234567890" \
        start=="2018-03-01T00:00:00" \
        end=="2018-04-01T00:00:00"

Response:

::

    HTTP/1.1 404 Not Found
    Allow: GET, HEAD, OPTIONS
    Connection: keep-alive
    Content-Length: 23
    Content-Type: application/json
    Date: Mon, 19 Mar 2018 20:30:31 GMT
    Server: nginx/1.13.9
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "detail": "Not found."
    }

If you attempt to retrieve a report for a valid cloud provider but provide an
account ID that does not match the cloud's format, you should get a 400 error.

Request:

.. code:: bash

    http localhost:8080/api/v1/report/ "${AUTH}" \
        cloud_provider=="aws" \
        cloud_account_id=="NX-74205" \
        start=="2018-03-01T00:00:00" \
        end=="2018-04-01T00:00:00"

Response:

::

    HTTP/1.1 400 Bad Request
    Allow: GET, HEAD, OPTIONS
    Connection: keep-alive
    Content-Length: 132
    Content-Type: application/json
    Date: Mon, 19 Mar 2018 20:34:37 GMT
    Server: nginx/1.13.9
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "cloud_account_id": [
            "A valid number is required."
        ],
        "cloud_provider": [
            "Incorrect cloud_account_id type for cloud_provider \"aws\""
        ]
    }
