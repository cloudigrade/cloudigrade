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
-  ``/api/v1/event/`` returns event data
-  ``/api/v1/instance/`` returns instance data
-  ``/api/v1/image/`` returns image data
-  ``/api/v1/sysconfig/`` returns sysconfig data
-  ``/api/v1/user/`` returns user data
-  ``/api/v1/report/instances/`` returns daily instance usage data
-  ``/api/v1/report/accounts/`` returns account overview data
-  ``/api/v1/report/images/`` returns active images overview data
-  ``/auth/`` is for authentication

User Account Setup
------------------

This is for accounts with Cloudigrade itself, not telling Cloudigrade
about a user's AWS account.

Create a Cloudigrade account
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http post localhost:8080/auth/users/create/ \
    username=<username> password=<password>

Response:

::

    HTTP/1.1 201 Created
    Allow: POST, OPTIONS
    Content-Length: 43
    Content-Type: application/json
    Date: Thu, 10 May 2018 20:11:16 GMT
    Server: nginx/1.12.1
    Set-Cookie: 4bf7fdd75eecaf09c9580e6ddbe57ad4=3a0a5f9fe4f5acc709f37456c6867643; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "email": "",
        "id": <id>,
        "username": "<username>"
    }


Login to Cloudigrade
~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http post localhost:8080/auth/token/create/ \
    username=<username> password=<password>

Response:

::

    HTTP/1.1 200 OK
    Allow: POST, OPTIONS
    Content-Length: 57
    Content-Type: application/json
    Date: Thu, 10 May 2018 20:12:16 GMT
    Server: nginx/1.12.1
    Set-Cookie: 4bf7fdd75eecaf09c9580e6ddbe57ad4=3a0a5f9fe4f5acc709f37456c6867643; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "auth_token": "eb6bedd93ecb158ffdee76f185b90b25ab39a8e9"
    }

The `auth_token` should be used in the `Authorization:` HTTP header.

Log out of Cloudigrade
~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/auth/token/destroy/ "${AUTH}"

Response:

::

    HTTP/1.1 204 No Content
    Allow: POST, OPTIONS
    Content-Length: 0
    Date: Thu, 10 May 2018 20:13:32 GMT
    Server: nginx/1.12.1
    Set-Cookie: 4bf7fdd75eecaf09c9580e6ddbe57ad4=3a0a5f9fe4f5acc709f37456c6867643; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN


Customer Account Setup
----------------------

Create an AWS account
~~~~~~~~~~~~~~~~~~~~~

This request may take a few seconds because of multiple round-trip calls
to the AWS APIs for each region. The "name" attribute is optional and has a
maximum supported length of 256 characters.

Request:

.. code:: bash

    http post localhost:8080/api/v1/account/ "${AUTH}" \
        resourcetype="AwsAccount" \
        account_arn="arn:aws:iam::273470430754:role/role-for-cloudigrade" \
        name="My Favorite Account"

Response:

::

    HTTP/1.1 201 Created
    Allow: GET, POST, HEAD, OPTIONS
    Content-Length: 311
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:00:25 GMT
    Location: http://localhost:8080/api/v1/account/3/
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
        "aws_account_id": "273470430754",
        "created_at": "2018-07-05T16:00:24.473331Z",
        "id": 3,
        "name": "My Favorite Account",
        "resourcetype": "AwsAccount",
        "updated_at": "2018-07-05T16:00:24.473360Z",
        "url": "http://localhost:8080/api/v1/account/3/",
        "user_id": 2
    }

If not specified, the account is created with a ``null`` value for "name".

Request:

.. code:: bash

    http post localhost:8080/api/v1/account/ "${AUTH}" \
        resourcetype="AwsAccount" \
        account_arn="arn:aws:iam::273470430754:role/role-for-cloudigrade"

Response:

::

    HTTP/1.1 201 Created
    Allow: GET, POST, HEAD, OPTIONS
    Content-Length: 294
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:01:30 GMT
    Location: http://localhost:8080/api/v1/account/4/
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
        "aws_account_id": "273470430754",
        "created_at": "2018-07-05T16:01:30.046877Z",
        "id": 4,
        "name": null,
        "resourcetype": "AwsAccount",
        "updated_at": "2018-07-05T16:01:30.046910Z",
        "url": "http://localhost:8080/api/v1/account/4/",
        "user_id": 2
    }

If you attempt to create an AWS account for an ARN that is already in
the system, you should get a 400 error.

Request:

.. code:: bash

    http post localhost:8080/api/v1/account/ "${AUTH}" \
        resourcetype="AwsAccount" \
        account_arn="arn:aws:iam::273470430754:role/role-for-cloudigrade"

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
    Content-Length: 346
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:06:47 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 1,
        "next": null,
        "previous": null,
        "results": [
            {
                "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
                "aws_account_id": "273470430754",
                "created_at": "2018-07-05T16:01:30.046877Z",
                "id": 4,
                "name": null,
                "resourcetype": "AwsAccount",
                "updated_at": "2018-07-05T16:01:30.046910Z",
                "url": "http://localhost:8080/api/v1/account/4/",
                "user_id": 2
            }
        ]
    }

Retrieve a specific account
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/account/4/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 294
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:07:16 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
        "aws_account_id": "273470430754",
        "created_at": "2018-07-05T16:01:30.046877Z",
        "id": 4,
        "name": null,
        "resourcetype": "AwsAccount",
        "updated_at": "2018-07-05T16:01:30.046910Z",
        "url": "http://localhost:8080/api/v1/account/4/",
        "user_id": 2
    }

Update a specific account
~~~~~~~~~~~~~~~~~~~~~~~~~

You can update the account object via either HTTP PATCH or HTTP PUT. All
updates require you to specify the "resourcetype".

At the time of this writing, only the "name" property can be changed on the
account object.

Request:

.. code:: bash

    http patch localhost:8080/api/v1/account/4/ "${AUTH}" \
        resourcetype="AwsAccount" \
        name="another name PATCHed in"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 315
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:07:47 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
        "aws_account_id": "273470430754",
        "created_at": "2018-07-05T16:01:30.046877Z",
        "id": 4,
        "name": "another name PATCHed in",
        "resourcetype": "AwsAccount",
        "updated_at": "2018-07-05T16:07:47.078088Z",
        "url": "http://localhost:8080/api/v1/account/4/",
        "user_id": 2
    }

Because PATCH is intended to replace objects, it must include all potentially
writable fields, which includes "name" and "account_arn".

Request:

.. code:: bash

    http put localhost:8080/api/v1/account/4/ "${AUTH}" \
        resourcetype="AwsAccount" \
        name="this name was PUT in its place" \
        account_arn="arn:aws:iam::273470430754:role/role-for-cloudigrade"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 322
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:08:44 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
        "aws_account_id": "273470430754",
        "created_at": "2018-07-05T16:01:30.046877Z",
        "id": 4,
        "name": "this name was PUT in its place",
        "resourcetype": "AwsAccount",
        "updated_at": "2018-07-05T16:08:44.004473Z",
        "url": "http://localhost:8080/api/v1/account/4/",
        "user_id": 2
    }

You cannot change the ARN via PUT or PATCH.

Request:

.. code:: bash

    http patch localhost:8080/api/v1/account/4/ "${AUTH}" \
        resourcetype="AwsAccount" \
        account_arn="arn:aws:iam::999999999999:role/role-for-cloudigrade"

Response:

::

    HTTP/1.1 400 Bad Request
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 49
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:12:12 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": [
            "You cannot change this field."
        ]
    }

Instance Info
-------------

List all instances
~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http https://test.cloudigra.de/api/v1/instance/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 3053
    Content-Type: application/json
    Date: Thu, 16 Aug 2018 17:41:39 GMT
    Server: nginx/1.12.1
    Set-Cookie: 0363cac70e8248650afc0b0855f64be8=fb0364ad8de0070c1eb515b3b092ee1c; path=/; HttpOnly; Secure
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 3,
        "next": null,
        "previous": null,
        "results": [
            {
                "account": "https://test.cloudigra.de/api/v1/account/3/",
                "account_id": 3,
                "created_at": "2018-08-08T17:09:22.879395Z",
                "ec2_instance_id": "i-08f57804410734024",
                "id": 1,
                "region": "us-east-1",
                "resourcetype": "AwsInstance",
                "updated_at": "2018-08-08T17:09:22.879414Z",
                "url": "https://test.cloudigra.de/api/v1/instance/1/"
            },
            {
                "account": "https://test.cloudigra.de/api/v1/account/3/",
                "account_id": 3,
                "created_at": "2018-08-08T17:41:35.437117Z",
                "ec2_instance_id": "i-09f905a808748efc7",
                "id": 2,
                "region": "us-east-1",
                "resourcetype": "AwsInstance",
                "updated_at": "2018-08-08T17:41:35.437135Z",
                "url": "https://test.cloudigra.de/api/v1/instance/2/"
            },
            {
                "account": "https://test.cloudigra.de/api/v1/account/3/",
                "account_id": 3,
                "created_at": "2018-08-08T18:03:35.524515Z",
                "ec2_instance_id": "i-01b6d5b1c7c60bf18",
                "id": 3,
                "region": "us-east-1",
                "resourcetype": "AwsInstance",
                "updated_at": "2018-08-08T18:03:35.524532Z",
                "url": "https://test.cloudigra.de/api/v1/instance/3/"
            }
        ]
    }

Retrieve a specific instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http https://test.cloudigra.de/api/v1/instance/1/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 293
    Content-Type: application/json
    Date: Thu, 16 Aug 2018 17:43:56 GMT
    Server: nginx/1.12.1
    Set-Cookie: 0363cac70e8248650afc0b0855f64be8=fb0364ad8de0070c1eb515b3b092ee1c; path=/; HttpOnly; Secure
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account": "https://test.cloudigra.de/api/v1/account/3/",
        "account_id": 3,
        "created_at": "2018-08-08T17:09:22.879395Z",
        "ec2_instance_id": "i-08f57804410734024",
        "id": 1,
        "region": "us-east-1",
        "resourcetype": "AwsInstance",
        "updated_at": "2018-08-08T17:09:22.879414Z",
        "url": "https://test.cloudigra.de/api/v1/instance/1/"
    }

Filtering instances
~~~~~~~~~~~~~~~~~~~

You may include an optional "user_id" query string argument to filter results
down to a specific user.

Request:

.. code:: bash

    http https://test.cloudigra.de/api/v1/instance/ "${AUTH}" \
        user_id==6

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 345
    Content-Type: application/json
    Date: Thu, 16 Aug 2018 17:46:43 GMT
    Server: nginx/1.12.1
    Set-Cookie: 0363cac70e8248650afc0b0855f64be8=cfa68a8ba45bf7df1382f5de98e2204f; path=/; HttpOnly; Secure
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 1,
        "next": null,
        "previous": null,
        "results": [
            {
                "account": "https://test.cloudigra.de/api/v1/account/4/",
                "account_id": 4,
                "created_at": "2018-08-09T18:48:37.444729Z",
                "ec2_instance_id": "i-0e0eb03041e117b2d",
                "id": 7,
                "region": "us-east-2",
                "resourcetype": "AwsInstance",
                "updated_at": "2018-08-09T18:48:37.444747Z",
                "url": "https://test.cloudigra.de/api/v1/instance/7/"
            }
        ]
    }

Instance Event Info
-------------------

List all events
~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http https://test.cloudigra.de/api/v1/event/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 2825
    Content-Type: application/json
    Date: Thu, 16 Aug 2018 14:58:24 GMT
    Server: nginx/1.12.1
    Set-Cookie: 0363cac70e8248650afc0b0855f64be8=fb0364ad8de0070c1eb515b3b092ee1c; path=/; HttpOnly; Secure
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 5,
        "next": "https://test.cloudigra.de/api/v1/event/?limit=10&offset=10",
        "previous": null,
        "results": [
            {
                "event_type": "power_on",
                "id": 1,
                "instance": "https://test.cloudigra.de/api/v1/instance/1/",
                "instance_id": 1,
                "instance_type": "t2.micro",
                "machineimage": "https://test.cloudigra.de/api/v1/image/1/",
                "machineimage_id": 1,
                "occurred_at": "2018-08-08T17:02:55Z",
                "resourcetype": "AwsInstanceEvent",
                "subnet": "subnet-8134e1af",
                "url": "https://test.cloudigra.de/api/v1/event/1/"
            },
            {
                "event_type": "power_off",
                "id": 2,
                "instance": "https://test.cloudigra.de/api/v1/instance/1/",
                "instance_id": 1,
                "instance_type": "t2.micro",
                "machineimage": "https://test.cloudigra.de/api/v1/image/1/",
                "machineimage_id": 1,
                "occurred_at": "2018-08-08T17:11:52Z",
                "resourcetype": "AwsInstanceEvent",
                "subnet": null,
                "url": "https://test.cloudigra.de/api/v1/event/2/"
            },
            {
                "event_type": "power_on",
                "id": 3,
                "instance": "https://test.cloudigra.de/api/v1/instance/2/",
                "instance_id": 2,
                "instance_type": "t2.micro",
                "machineimage": "https://test.cloudigra.de/api/v1/image/2/",
                "machineimage_id": 2,
                "occurred_at": "2018-08-08T17:29:54Z",
                "resourcetype": "AwsInstanceEvent",
                "subnet": "subnet-8134e1af",
                "url": "https://test.cloudigra.de/api/v1/event/3/"
            },
            {
                "event_type": "power_on",
                "id": 4,
                "instance": "https://test.cloudigra.de/api/v1/instance/3/",
                "instance_id": 3,
                "instance_type": "t2.micro",
                "machineimage": "https://test.cloudigra.de/api/v1/image/3/",
                "machineimage_id": 3,
                "occurred_at": "2018-08-08T17:56:02Z",
                "resourcetype": "AwsInstanceEvent",
                "subnet": "subnet-26fe357a",
                "url": "https://test.cloudigra.de/api/v1/event/4/"
            },
            {
                "event_type": "power_on",
                "id": 5,
                "instance": "https://test.cloudigra.de/api/v1/instance/4/",
                "instance_id": 4,
                "instance_type": "t1.micro",
                "machineimage": "https://test.cloudigra.de/api/v1/image/4/",
                "machineimage_id": 4,
                "occurred_at": "2018-08-08T18:20:59Z",
                "resourcetype": "AwsInstanceEvent",
                "subnet": "subnet-e6059aac",
                "url": "https://test.cloudigra.de/api/v1/event/5/"
            }
        ]
    }

Retrieve a specific event
~~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http https://test.cloudigra.de/api/v1/event/1/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 274
    Content-Type: application/json
    Date: Thu, 16 Aug 2018 15:04:00 GMT
    Server: nginx/1.12.1
    Set-Cookie: 0363cac70e8248650afc0b0855f64be8=fb0364ad8de0070c1eb515b3b092ee1c; path=/; HttpOnly; Secure
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "event_type": "power_on",
        "id": 1,
        "instance": "https://test.cloudigra.de/api/v1/instance/1/",
        "instance_id": 1,
        "instance_type": "t2.micro",
        "machineimage": "https://test.cloudigra.de/api/v1/image/1/",
        "machineimage_id": 1,
        "occurred_at": "2018-08-08T17:02:55Z",
        "resourcetype": "AwsInstanceEvent",
        "subnet": "subnet-8134e1af",
        "url": "https://test.cloudigra.de/api/v1/event/1/"
    }

Filtering events
~~~~~~~~~~~~~~~~

You may include an optional "instance_id" query string argument to filter results
down to a specific instance.

Request:

.. code:: bash

    http https://test.cloudigra.de/api/v1/event/ "${AUTH}" \
        instance_id==1

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 589
    Content-Type: application/json
    Date: Thu, 16 Aug 2018 15:21:21 GMT
    Server: nginx/1.12.1
    Set-Cookie: 0363cac70e8248650afc0b0855f64be8=cfa68a8ba45bf7df1382f5de98e2204f; path=/; HttpOnly; Secure
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 2,
        "next": null,
        "previous": null,
        "results": [
            {
                "event_type": "power_on",
                "id": 1,
                "instance": "https://test.cloudigra.de/api/v1/instance/1/",
                "instance_id": 1,
                "instance_type": "t2.micro",
                "machineimage": "https://test.cloudigra.de/api/v1/image/1/",
                "machineimage_id": 1,
                "occurred_at": "2018-08-08T17:02:55Z",
                "resourcetype": "AwsInstanceEvent",
                "subnet": "subnet-8134e1af",
                "url": "https://test.cloudigra.de/api/v1/event/1/"
            },
            {
                "event_type": "power_off",
                "id": 2,
                "instance": "https://test.cloudigra.de/api/v1/instance/1/",
                "instance_id": 1,
                "instance_type": "t2.micro",
                "machineimage": "https://test.cloudigra.de/api/v1/image/1/",
                "machineimage_id": 1,
                "occurred_at": "2018-08-08T17:11:52Z",
                "resourcetype": "AwsInstanceEvent",
                "subnet": null,
                "url": "https://test.cloudigra.de/api/v1/event/2/"
            }
        ]
    }

You may include an optional "user_id" query string argument to filter results
down to a specific user.

Request:

.. code:: bash

    http https://test.cloudigra.de/api/v1/event/ "${AUTH}" \
        user_id==4

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 929
    Content-Type: application/json
    Date: Thu, 16 Aug 2018 15:22:57 GMT
    Server: nginx/1.12.1
    Set-Cookie: 0363cac70e8248650afc0b0855f64be8=fb0364ad8de0070c1eb515b3b092ee1c; path=/; HttpOnly; Secure
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 2,
        "next": null,
        "previous": null,
        "results": [
            {
                "event_type": "power_on",
                "id": 1,
                "instance": "https://test.cloudigra.de/api/v1/instance/1/",
                "instance_id": 1,
                "instance_type": "t2.micro",
                "machineimage": "https://test.cloudigra.de/api/v1/image/1/",
                "machineimage_id": 1,
                "occurred_at": "2018-08-08T17:02:55Z",
                "resourcetype": "AwsInstanceEvent",
                "subnet": "subnet-8134e1af",
                "url": "https://test.cloudigra.de/api/v1/event/1/"
            },
            {
                "event_type": "power_off",
                "id": 2,
                "instance": "https://test.cloudigra.de/api/v1/instance/1/",
                "instance_id": 1,
                "instance_type": "t2.micro",
                "machineimage": "https://test.cloudigra.de/api/v1/image/1/",
                "machineimage_id": 1,
                "occurred_at": "2018-08-08T17:11:52Z",
                "resourcetype": "AwsInstanceEvent",
                "subnet": null,
                "url": "https://test.cloudigra.de/api/v1/event/2/"
            }
        ]
    }

Usage Reporting
---------------

Retrieve a daily instance usage report
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You may include an optional "user_id" query string argument to filter results
down to a specific user if your request is authenticated as a superuser.

You may include an optional "name_pattern" query string argument to filter
results down to activity under accounts whose names match at least one of the
words in that argument.

Request:

.. code:: bash

    http localhost:8080/api/v1/report/instances/ "${AUTH}" \
        start=="2018-03-01T00:00:00" \
        end=="2018-03-04T00:00:00"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Length: 482
    Content-Type: application/json
    Date: Thu, 12 Jul 2018 22:10:35 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "daily_usage": [
            {
                "date": "2018-03-01T00:00:00Z",
                "openshift_instances": 0,
                "openshift_memory_seconds": 0.0,
                "openshift_runtime_seconds": 0.0,
                "openshift_vcpu_seconds": 0.0,
                "rhel_instances": 0,
                "rhel_memory_seconds": 0.0,
                "rhel_runtime_seconds": 0.0,
                "rhel_vcpu_seconds": 0.0
            },
            {
                "date": "2018-03-02T00:00:00Z",
                "openshift_instances": 0,
                "openshift_memory_seconds": 0.0,
                "openshift_runtime_seconds": 0.0,
                "openshift_vcpu_seconds": 0.0,
                "rhel_instances": 0,
                "rhel_memory_seconds": 0.0,
                "rhel_runtime_seconds": 0.0,
                "rhel_vcpu_seconds": 0.0
            },
            {
                "date": "2018-03-03T00:00:00Z",
                "openshift_instances": 0,
                "openshift_memory_seconds": 0.0,
                "openshift_runtime_seconds": 0.0,
                "openshift_vcpu_seconds": 0.0,
                "rhel_instances": 0,
                "rhel_memory_seconds": 0.0,
                "rhel_runtime_seconds": 0.0,
                "rhel_vcpu_seconds": 0.0
            }
        ],
        "instances_seen_with_openshift": 0,
        "instances_seen_with_rhel": 0
    }


Retrieve an account overview
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/report/accounts/ "${AUTH}" \
        start=="2018-03-01T00:00:00" \
        end=="2018-04-01T00:00:00"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Length: 483
    Content-Type: application/json
    Date: Fri, 06 Jul 2018 18:32:16 GMT
    Server: WSGIServer/0.2 CPython/3.6.4
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "cloud_account_overviews": [
            {
                "arn": "arn:aws:iam::114204391493:role/role-for-cloudigrade",
                "cloud_account_id": "114204391493",
                "creation_date": "2018-07-06T15:09:21.442412Z",
                "id": 1,
                "images": null,
                "instances": null,
                "name": "account-for-aiken",
                "openshift_images_challenged": null,
                "openshift_instances": null,
                "openshift_runtime_seconds": 0.0,
                "rhel_images_challenged": null,
                "rhel_instances": null,
                "rhel_runtime_seconds": 0.0,
                "type": "aws",
                "user_id": 1
            },
            ...
        ]
    }

If you attempt to retrieve cloud account overviews without specifying a
start and end date, you should get a 400 error.

Request:

.. code:: bash

    http localhost:8080/api/v1/report/accounts/ "${AUTH}"

Response:

::

    HTTP/1.1 400 Bad Request
    Allow: GET, HEAD, OPTIONS
    Content-Length: 71
    Content-Type: application/json
    Date: Fri, 06 Jul 2018 18:37:58 GMT
    Server: WSGIServer/0.2 CPython/3.6.4
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "end": [
            "This field is required."
        ],
        "start": [
            "This field is required."
        ]
    }

You may include an optional "name_pattern" query string argument to filter
results down to activity under accounts whose names match at least one of the
words in that argument.

You may include an optional "account_id" query string argument to filter
results down to activity for a specific clount (Cloud Account). This can be
combined with the "user_id" argument if the caller is a superuser to get
information specific to a different user.

In this example, an account named "greatest account ever" is included because
it contains the word "eat" even though it does not contain the word "tofu".

Request:

.. code:: bash

    http localhost:8080/api/v1/report/accounts/ "${AUTH}" \
        start=="2018-01-10T00:00:00" \
        end=="2018-01-15T00:00:00" \
        name_pattern=="eat tofu"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Length: 266
    Content-Type: application/json
    Date: Thu, 19 Jul 2018 21:13:57 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "cloud_account_overviews": [
            {
                "arn": "arn:aws:iam::058091732613:role/Marcus Colon",
                "cloud_account_id": "058091732613",
                "creation_date": "2018-01-01T00:00:00Z",
                "id": 5,
                "images": 3,
                "instances": 4,
                "name": "greatest account ever",
                "openshift_images_challenged": 0,
                "openshift_instances": 0,
                "openshift_runtime_seconds": 0.0,
                "rhel_images_challenged": 0,
                "rhel_instances": 2,
                "rhel_runtime_seconds": 200,
                "type": "aws",
                "user_id": 1
            }
        ]
    }


Retrieve an account's active images overview
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The "start", "end", and "account_id" query string arguments are all required.
If authenticated as a superuser, you may include an optional "user_id" query
string argument to get the results for that user.

Request:

.. code:: bash

    http localhost:8080/api/v1/report/images/ "${AUTH}" \
        start=="2018-01-10T00:00:00" \
        end=="2018-01-15T00:00:00" \
        account_id==1

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Length: 815
    Content-Type: application/json
    Date: Thu, 02 Aug 2018 18:51:10 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "images": [
            {
                "cloud_image_id": "ami-rhel7",
                "id": 2,
                "instances_seen": 2,
                "is_encrypted": false,
                "name": null,
                "openshift": false,
                "openshift_challenged": false,
                "openshift_detected": false,
                "rhel": true,
                "rhel_challenged": false,
                "rhel_detected": true,
                "runtime_seconds": 7200.0,
                "status": "inspected"
            },
            {
                "cloud_image_id": "ami-rhel8",
                "id": 3,
                "instances_seen": 1,
                "is_encrypted": false,
                "name": null,
                "openshift": false,
                "openshift_challenged": false,
                "openshift_detected": false,
                "rhel": true,
                "rhel_challenged": false,
                "rhel_detected": true,
                "runtime_seconds": 3600.0,
                "status": "inspected"
            },
            {
                "cloud_image_id": "ami-plain",
                "id": 1,
                "instances_seen": 1,
                "is_encrypted": false,
                "name": null,
                "openshift": false,
                "openshift_challenged": false,
                "openshift_detected": false,
                "rhel": false,
                "rhel_challenged": false,
                "rhel_detected": false,
                "runtime_seconds": 3600.0,
                "status": "inspected"
            }
        ]
    }


User Info
---------------------

List all users
~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/user/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 399
    Content-Type: application/json
    Date: Thu, 16 Aug 2018 01:11:16 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=9d142a0cc3d9498f8726c1d498f28b7a; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    [
        {
            "accounts": 0,
            "challenged_images": 0,
            "id": 1,
            "is_superuser": true,
            "username": "XiTleKxGfiqoiTFbEZJnWJnhYJlxioAO@mail.127.0.0.1.nip.io"
        },
        {
            "accounts": 1,
            "challenged_images": 2,
            "id": 2,
            "is_superuser": false,
            "username": "iLdlWmZciaaQifUEyDSTXlmMLpbhQXhc@mail.127.0.0.1.nip.io"
        },
        {
            "accounts": 1,
            "challenged_images": 1,
            "id": 3,
            "is_superuser": false,
            "username": "ehURjMBDhhbeSxcYdrGPVTJQoxGBfYUh@mail.127.0.0.1.nip.io"
        }
    ]

Retrieve a specific user
~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/user/2/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 132
    Content-Type: application/json
    Date: Thu, 16 Aug 2018 01:11:27 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=9d142a0cc3d9498f8726c1d498f28b7a; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "accounts": 1,
        "challenged_images": 2,
        "id": 2,
        "is_superuser": false,
        "username": "iLdlWmZciaaQifUEyDSTXlmMLpbhQXhc@mail.127.0.0.1.nip.io"
    }


Machine Images
--------------
Listing Images
~~~~~~~~~~~~~~

Below command will return all images that have been seen used by any instance for any account belonging to the user that makes the request.

Request:

.. code:: bash

    http get http://cloudigrade.127.0.0.1.nip.io/api/v1/image/ Authorization:"Token ${USER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 1610
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:20:26 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 4,
        "next": null,
        "previous": null,
        "results": [
            {
                "created_at": "2018-07-30T15:41:16.310031Z",
                "ec2_ami_id": "ami-plain",
                "id": 1,
                "inspection_json": "{\"/dev/xvdbb\": {\"/dev/xvdbb1\": {\"facts\": {\"rhel_enabled_repos\": {\"rhel_enabled_repos\": [], \"rhel_found\": false}, \"rhel_product_certs\": {\"rhel_found\": false, \"rhel_pem_files\": []}, \"rhel_release_files\": {\"rhel_found\": false, \"status\": \"No release files found on /dev/xvdbb1\"}, \"rhel_signed_packages\": {\"rhel_found\": false, \"rhel_signed_package_count\": 0}}}}, \"rhel_enabled_repos_found\": false, \"rhel_found\": true, \"rhel_product_certs_found\": false, \"rhel_release_files_found\": true, \"rhel_signed_packages_found\": false}",
                "is_encrypted": false,
                "name": "my favorite image",
                "openshift": false,
                "openshift_challenged": false,
                "openshift_detected": false,
                "owner_aws_account_id": "273470430754",
                "platform": "none",
                "resourcetype": "AwsMachineImage",
                "rhel": false,
                "rhel_challenged": false,
                "rhel_detected": false,
                "rhel_enabled_repos_found": false,
                "rhel_product_certs_found": false,
                "rhel_release_files_found": false,
                "rhel_signed_packages_found": false,
                "status": "inspected",
                "updated_at": "2018-07-30T15:15:11.214092Z",
                "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/"
            },
            {
                "created_at": "2018-07-30T15:41:16.317326Z",
                "ec2_ami_id": "ami-rhel7",
                "id": 2,
                "inspection_json": null,
                "is_encrypted": false,
                "name": null,
                "openshift": true,
                "openshift_challenged": true,
                "openshift_detected": false,
                "owner_aws_account_id": "273470430754",
                "platform": "none",
                "resourcetype": "AwsMachineImage",
                "rhel": false,
                "rhel_challenged": true,
                "rhel_detected": false,
                "rhel_enabled_repos_found": false,
                "rhel_product_certs_found": false,
                "rhel_release_files_found": false,
                "rhel_signed_packages_found": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:14:19.829340Z",
                "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/2/"
            },
            {
                "created_at": "2018-07-30T15:41:16.330278Z",
                "ec2_ami_id": "ami-openshift",
                "id": 3,
                "inspection_json": null,
                "is_encrypted": false,
                "name": null,
                "openshift": false,
                "openshift_challenged": true,
                "openshift_detected": true,
                "owner_aws_account_id": "273470430754",
                "platform": "none",
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": true,
                "rhel_detected": false,
                "rhel_enabled_repos_found": false,
                "rhel_product_certs_found": false,
                "rhel_release_files_found": false,
                "rhel_signed_packages_found": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:14:06.164469Z",
                "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/3/"
            },
            {
                "created_at": "2018-07-30T15:41:16.343734Z",
                "ec2_ami_id": "ami-both",
                "id": 4,
                "inspection_json": null,
                "is_encrypted": false,
                "name": null,
                "openshift": true,
                "openshift_challenged": false,
                "openshift_detected": true,
                "owner_aws_account_id": "273470430754",
                "platform": "none",
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": false,
                "rhel_detected": false,
                "rhel_enabled_repos_found": false,
                "rhel_product_certs_found": false,
                "rhel_release_files_found": false,
                "rhel_signed_packages_found": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:41:16.355784Z",
                "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/4/"
            }
        ]
    }

A superuser will see all images used by instances in all accounts.

Request:

.. code:: bash

    http get http://cloudigrade.127.0.0.1.nip.io/api/v1/image/ Authorization:"Token ${SUPER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 2005
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:23:25 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 5,
        "next": null,
        "previous": null,
        "results": [
            {
                "created_at": "2018-07-30T15:41:16.310031Z",
                "ec2_ami_id": "ami-plain",
                "id": 1,
                "inspection_json": "{\"/dev/xvdbb\": {\"/dev/xvdbb1\": {\"facts\": {\"rhel_enabled_repos\": {\"rhel_enabled_repos\": [], \"rhel_found\": false}, \"rhel_product_certs\": {\"rhel_found\": false, \"rhel_pem_files\": []}, \"rhel_release_files\": {\"rhel_found\": false, \"status\": \"No release files found on /dev/xvdbb1\"}, \"rhel_signed_packages\": {\"rhel_found\": false, \"rhel_signed_package_count\": 0}}}}, \"rhel_enabled_repos_found\": false, \"rhel_found\": true, \"rhel_product_certs_found\": false, \"rhel_release_files_found\": true, \"rhel_signed_packages_found\": false}",
                "is_encrypted": false,
                "name": "my favorite image",
                "openshift": false,
                "openshift_challenged": false,
                "openshift_detected": false,
                "owner_aws_account_id": "273470430754",
                "platform": "none",
                "resourcetype": "AwsMachineImage",
                "rhel": false,
                "rhel_challenged": false,
                "rhel_detected": false,
                "rhel_enabled_repos_found": false,
                "rhel_product_certs_found": false,
                "rhel_release_files_found": false,
                "rhel_signed_packages_found": false,
                "status": "inspected",
                "updated_at": "2018-07-30T15:15:11.214092Z",
                "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/"
            },
            {
                "created_at": "2018-07-30T15:41:16.317326Z",
                "ec2_ami_id": "ami-rhel7",
                "id": 2,
                "inspection_json": null,
                "is_encrypted": false,
                "name": null,
                "openshift": true,
                "openshift_challenged": true,
                "openshift_detected": false,
                "owner_aws_account_id": "273470430754",
                "platform": "none",
                "resourcetype": "AwsMachineImage",
                "rhel": false,
                "rhel_challenged": true,
                "rhel_detected": false,
                "rhel_enabled_repos_found": false,
                "rhel_product_certs_found": false,
                "rhel_release_files_found": false,
                "rhel_signed_packages_found": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:14:19.829340Z",
                "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/2/"
            },
            {
                "created_at": "2018-07-30T15:41:16.330278Z",
                "ec2_ami_id": "ami-openshift",
                "id": 3,
                "inspection_json": null,
                "is_encrypted": false,
                "name": null,
                "openshift": false,
                "openshift_challenged": true,
                "openshift_detected": true,
                "owner_aws_account_id": "273470430754",
                "platform": "none",
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": true,
                "rhel_detected": false,
                "rhel_enabled_repos_found": false,
                "rhel_product_certs_found": false,
                "rhel_release_files_found": false,
                "rhel_signed_packages_found": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:14:06.164469Z",
                "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/3/"
            },
            {
                "created_at": "2018-07-30T15:41:16.343734Z",
                "ec2_ami_id": "ami-both",
                "id": 4,
                "inspection_json": null,
                "is_encrypted": false,
                "name": null,
                "openshift": true,
                "openshift_challenged": false,
                "openshift_detected": true,
                "owner_aws_account_id": "273470430754",
                "platform": "none",
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": false,
                "rhel_detected": false,
                "rhel_enabled_repos_found": false,
                "rhel_product_certs_found": false,
                "rhel_release_files_found": false,
                "rhel_signed_packages_found": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:41:16.355784Z",
                "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/4/"
            },
            {
                "created_at": "2018-07-30T15:41:16.362110Z",
                "ec2_ami_id": "ami-rhel_other",
                "id": 5,
                "inspection_json": null,
                "is_encrypted": false,
                "name": null,
                "openshift": false,
                "openshift_challenged": false,
                "openshift_detected": false,
                "owner_aws_account_id": "518028203513",
                "platform": "none",
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": false,
                "rhel_detected": false,
                "rhel_enabled_repos_found": false,
                "rhel_product_certs_found": false,
                "rhel_release_files_found": false,
                "rhel_signed_packages_found": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:41:16.367853Z",
                "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/5/"
            }
        ]
    }

A superuser can also filter the images down to a those used by instances for accounts belonging to a specific user by using the optional
``user_id`` query string argument.

Request:

.. code:: bash

    http get http://cloudigrade.127.0.0.1.nip.io/api/v1/image/ user_id==2 Authorization:"Token ${SUPER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 446
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:26:30 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 1,
        "next": null,
        "previous": null,
        "results": [
            {
                "created_at": "2018-07-30T15:41:16.362110Z",
                "ec2_ami_id": "ami-rhel_other",
                "id": 5,
                "inspection_json": null,
                "is_encrypted": false,
                "name": null,
                "openshift": false,
                "openshift_challenged": false,
                "openshift_detected": false,
                "owner_aws_account_id": "518028203513",
                "platform": "none",
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": false,
                "rhel_detected": false,
                "rhel_enabled_repos_found": false,
                "rhel_product_certs_found": false,
                "rhel_release_files_found": false,
                "rhel_signed_packages_found": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:41:16.367853Z",
                "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/5/"
            }
        ]
    }

Listing a Specific Image
~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http get http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/ Authorization:"Token ${USER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 391
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:29:04 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "created_at": "2018-07-30T15:41:16.310031Z",
        "ec2_ami_id": "ami-plain",
        "id": 1,
        "inspection_json": "{\"/dev/xvdbb\": {\"/dev/xvdbb1\": {\"facts\": {\"rhel_enabled_repos\": {\"rhel_enabled_repos\": [], \"rhel_found\": false}, \"rhel_product_certs\": {\"rhel_found\": false, \"rhel_pem_files\": []}, \"rhel_release_files\": {\"rhel_found\": false, \"status\": \"No release files found on /dev/xvdbb1\"}, \"rhel_signed_packages\": {\"rhel_found\": false, \"rhel_signed_package_count\": 0}}}}, \"rhel_enabled_repos_found\": false, \"rhel_found\": true, \"rhel_product_certs_found\": false, \"rhel_release_files_found\": true, \"rhel_signed_packages_found\": false}",
        "is_encrypted": false,
        "name": "my favorite image",
        "openshift": false,
        "openshift_challenged": false,
        "openshift_detected": false,
        "owner_aws_account_id": "273470430754",
        "platform": "none",
        "resourcetype": "AwsMachineImage",
        "rhel": false,
        "rhel_challenged": false,
        "rhel_detected": false,
        "rhel_enabled_repos_found": false,
        "rhel_product_certs_found": false,
        "rhel_release_files_found": false,
        "rhel_signed_packages_found": false,
        "status": "inspected",
        "updated_at": "2018-07-30T15:15:11.214092Z",
        "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/"
    }

Same, as a superuser.

Request:

.. code:: bash

    http get http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/ Authorization:"Token ${SUPER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 391
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:28:16 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "created_at": "2018-07-30T15:41:16.310031Z",
        "ec2_ami_id": "ami-plain",
        "id": 1,
        "inspection_json": "{\"/dev/xvdbb\": {\"/dev/xvdbb1\": {\"facts\": {\"rhel_enabled_repos\": {\"rhel_enabled_repos\": [], \"rhel_found\": false}, \"rhel_product_certs\": {\"rhel_found\": false, \"rhel_pem_files\": []}, \"rhel_release_files\": {\"rhel_found\": false, \"status\": \"No release files found on /dev/xvdbb1\"}, \"rhel_signed_packages\": {\"rhel_found\": false, \"rhel_signed_package_count\": 0}}}}, \"rhel_enabled_repos_found\": false, \"rhel_found\": true, \"rhel_product_certs_found\": false, \"rhel_release_files_found\": true, \"rhel_signed_packages_found\": false}",
        "is_encrypted": false,
        "name": "my favorite image",
        "openshift": false,
        "openshift_challenged": false,
        "openshift_detected": false,
        "owner_aws_account_id": "273470430754",
        "platform": "none",
        "resourcetype": "AwsMachineImage",
        "rhel": false,
        "rhel_challenged": false,
        "rhel_detected": false,
        "rhel_enabled_repos_found": false,
        "rhel_product_certs_found": false,
        "rhel_release_files_found": false,
        "rhel_signed_packages_found": false,
        "status": "inspected",
        "updated_at": "2018-07-30T15:15:11.214092Z",
        "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/"
    }

Issuing Challenges
~~~~~~~~~~~~~~~~~~
Note that ``resourcetype`` is required when making these calls.

Request:

.. code:: bash

    http patch http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/ \
        resourcetype=AwsMachineImage \
        rhel_challenged=True \
        Authorization:"Token ${USER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 389
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:31:02 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "created_at": "2018-07-30T15:41:16.310031Z",
        "ec2_ami_id": "ami-plain",
        "id": 1,
        "inspection_json": null,
        "is_encrypted": false,
        "name": null,
        "openshift": false,
        "openshift_challenged": false,
        "openshift_detected": false,
        "owner_aws_account_id": "273470430754",
        "platform": "none",
        "resourcetype": "AwsMachineImage",
        "rhel": true,
        "rhel_challenged": true,
        "rhel_detected": false,
        "rhel_enabled_repos_found": false,
        "rhel_product_certs_found": false,
        "rhel_release_files_found": false,
        "rhel_signed_packages_found": false,
        "status": "pending",
        "updated_at": "2018-07-30T15:31:02.026393Z",
        "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/"
    }

If you'd like to remove a challenge, simply send the same challenge with False as the value.

Request:

.. code:: bash

    http patch http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/ \
        resourcetype=AwsMachineImage \
        rhel_challenged=False \
        Authorization:"Token ${USER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 389
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:31:02 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "created_at": "2018-07-30T15:41:16.310031Z",
        "ec2_ami_id": "ami-plain",
        "id": 1,
        "inspection_json": null,
        "is_encrypted": false,
        "name": null,
        "openshift": false,
        "openshift_challenged": false,
        "openshift_detected": false,
        "owner_aws_account_id": "273470430754",
        "platform": "none",
        "resourcetype": "AwsMachineImage",
        "rhel": false,
        "rhel_challenged": false,
        "rhel_detected": false,
        "rhel_enabled_repos_found": false,
        "rhel_product_certs_found": false,
        "rhel_release_files_found": false,
        "rhel_signed_packages_found": false,
        "status": "pending",
        "updated_at": "2018-07-30T15:31:02.026393Z",
        "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/"
    }

You can challenge both at the same time.

Request:

.. code:: bash

    http patch http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/ \
        resourcetype=AwsMachineImage \
        rhel_challenged=True \
        openshift_challenged=True \
        Authorization:"Token ${USER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 389
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:31:02 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "created_at": "2018-07-30T15:41:16.310031Z",
        "ec2_ami_id": "ami-plain",
        "id": 1,
        "inspection_json": null,
        "is_encrypted": false,
        "name": null,
        "openshift": true,
        "openshift_challenged": true,
        "openshift_detected": false,
        "owner_aws_account_id": "273470430754",
        "platform": "none",
        "resourcetype": "AwsMachineImage",
        "rhel": true,
        "rhel_challenged": true,
        "rhel_detected": false,
        "rhel_enabled_repos_found": false,
        "rhel_product_certs_found": false,
        "rhel_release_files_found": false,
        "rhel_signed_packages_found": false,
        "status": "pending",
        "updated_at": "2018-07-30T15:31:02.026393Z",
        "url": "http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/"
    }

Miscellaneous Commands
----------------------

Retrieve current cloud account ids used by the application
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/sysconfig/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Length: 33
    Content-Type: application/json
    Date: Mon, 25 Jun 2018 17:22:50 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "aws_account_id": "123456789012",
        "aws_policies": {
            "traditional_inspection": {
                "Statement": [
                    {
                        "Action": [
                            "ec2:DescribeImages",
                            "ec2:DescribeInstances",
                            "ec2:ModifySnapshotAttribute",
                            "ec2:DescribeSnapshotAttribute",
                            "ec2:DescribeSnapshots",
                            "ec2:CopyImage",
                            "ec2:CreateTags",
                            "cloudtrail:CreateTrail",
                            "cloudtrail:UpdateTrail",
                            "cloudtrail:PutEventSelectors",
                            "cloudtrail:DescribeTrails",
                            "cloudtrail:StartLogging",
                            "cloudtrail:StopLogging"
                        ],
                        "Effect": "Allow",
                        "Resource": "*",
                        "Sid": "CloudigradePolicy"
                    }
                ],
                "Version": "2012-10-17"
            }
        },
        "version": "489-cloudigrade-version - d2b30c637ce3788e22990b21434bac2edcfb7ede"
    }

If your application was not deployed by gitlab-ci, version will not be available.

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Length: 33
    Content-Type: application/json
    Date: Mon, 25 Jun 2018 17:22:50 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "aws_account_id": "123456789012",
        "aws_policies": {
            "traditional_inspection": {
                "Statement": [
                    {
                        "Action": [
                            "ec2:DescribeImages",
                            "ec2:DescribeInstances",
                            "ec2:ModifySnapshotAttribute",
                            "ec2:DescribeSnapshotAttribute",
                            "ec2:DescribeSnapshots",
                            "ec2:CopyImage",
                            "ec2:CreateTags",
                            "cloudtrail:CreateTrail",
                            "cloudtrail:UpdateTrail",
                            "cloudtrail:PutEventSelectors",
                            "cloudtrail:DescribeTrails",
                            "cloudtrail:StartLogging",
                            "cloudtrail:StopLogging"
                        ],
                        "Effect": "Allow",
                        "Resource": "*",
                        "Sid": "CloudigradePolicy"
                    }
                ],
                "Version": "2012-10-17"
            }
        },
        "version": null
    }

If you attempt to retrieve account ids without authentication you'll receive a 401 error.
