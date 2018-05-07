********************************************
Steps for customer to create an AWS Role ARN
********************************************

Create Policy
=============

#. Go `here to start creating the policy <https://console.aws.amazon.com/iam/home#/policies$new?step=edit>`_  *or*

   #. log in to AWS console
   #. search Services to go to IAM
   #. click Policies in the left nav
   #. click the "Create policy" button

#. Click JSON to switch to the text editor.
#. Replace the contents of the text editor with the following:

   .. code-block:: json

       {
           "Version": "2012-10-17",
           "Statement": [
               {
                   "Sid": "VisualEditor0",
                   "Effect": "Allow",
                   "Action": [
                       "ec2:DescribeImages",
                       "ec2:DescribeInstances",
                       "ec2:ModifySnapshotAttribute",
                       "ec2:DescribeSnapshotAttribute",
                       "ec2:ModifyImageAttribute",
                       "ec2:DescribeSnapshots"
                   ],
                   "Resource": "*"
               }
           ]
       }

#. Click "Review policy".
#. Give the policy a distinct, memorable name such as ``policy-for-cloudigrade``. Copy this name for reference because you will need it soon.
#. Click "Create policy".


Create Role
===========

#. Go `here to start creating the role <https://console.aws.amazon.com/iam/home?#/roles$new?step=type&roleType=crossAccount&accountID=372779871274>`_  *or*

   #. log in to AWS console
   #. search Services to go to IAM
   #. click Roles in the left nav
   #. click the "Create role" button
   #. Click "Another AWS account"
   #. Paste this number into the Account ID field: ``372779871274``

#. Click "Next: Permissions".
#. Enter your new policy's name in the search box (e.g. ``policy-for-cloudigrade``)
#. Check the box for the policy.
#. Click "Next: Review".
#. Give the role a distinct, memorable name such as ``role-for-cloudigrade``.
#. Click "Create role".
#. From the Roles list page, click the role name you just created.
#. Copy the generated value for "Role ARN".
