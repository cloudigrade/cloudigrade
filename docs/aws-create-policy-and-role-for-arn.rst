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
                       "ec2:DescribeInstances",
                       "ec2:DescribeImages",
                       "ec2:DescribeSnapshots",
                       "ec2:ModifySnapshotAttribute",
                       "ec2:DescribeSnapshotAttribute",
                       "cloudtrail:CreateTrail",
                       "cloudtrail:UpdateTrail",
                       "cloudtrail:PutEventSelectors",
                       "cloudtrail:DescribeTrails",
                       "cloudtrail:StartLogging"
                   ],
                   "Resource": "*"
               }
           ]
       }

   .. note::
       cloudigrade needs each of these actions in order to identify and track relevant software products:

       - `ec2:DescribeInstances <https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html>`_ enables cloudigrade to get information about your currently running instances.
       - `ec2:DescribeImages <https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeImages.html>`_ enables cloudigrade to get information about the AMIs used to start your instances.
       - `ec2:DescribeSnapshots <https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSnapshots.html>`_ enables cloudigrade to get information about snapshots for those AMIs.
       - `ec2:ModifySnapshotAttribute <https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_ModifySnapshotAttribute.html>`_ enables cloudigrade to set an attribute that allows cloudigrade to copy snapshots for inspection.
       - `ec2:DescribeSnapshotAttribute <https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSnapshotAttribute.html>`_ enables cloudigrade to verify that it has set the aforementioned attribute.
       - `cloudtrail:CreateTrail <https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_CreateTrail.html>`_ enables cloudigrade to get information about existing cloudtrails
       - `cloudtrail:UpdateTrail <https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_UpdateTrail.html>`_ enables cloudigrade to turn on logging for cloudtrail
       - `cloudtrail:PutEventSelectors <https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_PutEventSelectors.html>`_ enables cloudigrade to create a cloudtrail in your account
       - `cloudtrail:DescribeTrails <https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_DescribeTrails.html>`_ enables cloudigrade to update a cloudtrail in your account
       - `cloudtrail:StartLogging <https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_StartLogging.html>`_ enables cloudigrade to select the events that cloudtrail cares about

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
