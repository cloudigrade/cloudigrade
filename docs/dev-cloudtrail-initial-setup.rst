***********************************
AWS S3 and SQS setup for CloudTrail
***********************************

S3 setup
========
#. log in to the AWS web console for the account running the ECS houndigrade cluster
#. go to the s3 (Simple Storage Service) page
#. click "Create bucket"
#. enter a name for your bucket matching the following format "`AWS_NAME_PREFIX`cloudigrade-s3"
.. note::
       the `AWS_NAME_PREFIX` already has a "-" at the end so for example if my `AWS_NAME_PREFIX` is "aaiken-" then I would name my s3 bucket "aaiken-cloudigrade-s3"
#. select a region (us-east-1) and click "Next"
#. the default properties and permissions are OK, click "Next" until you reach the "Review" step
#. click "Create bucket"
#. once you have created your bucket, select it by clicking on the block (not directly on the bucket name) to bring up a side bar
#. at the top of the bar select the option "Copy Bucket ARN"
#. save your bucket ARN as you will need it for later in the setup

SQS setup
=========
#. navigate to the SQS (Simple Queue Service) page
#. click "Create New Queue"
#. give the queue a reasonably unique name ("yourname-cloudigrade-sqs")
#. select Standard Queue and click "Quick-Create Queue"
#. select your queue and navigate to the "Details" tab
#. copy your queue ARN and save it for use later in the setup
#. with your queue still selected, click on the "Permissions" tab
#. click "Edit Policy Document (Advanced)"
#. click JSON to switch to the text editor.
#. replace the contents of the text editor with the following:

   .. code-block:: json

       {
          "Version": "2012-10-17",
          "Id": "CHANGE_TO_UNIQUE_ID",
          "Statement": [
            {
              "Sid": "CHANGE_TO_UNIQUE_ID",
              "Effect": "Allow",
              "Principal": {
                "AWS": "*"
              },
              "Action": "SQS:SendMessage",
              "Resource": "CHANGE_TO_ARN_FOR_YOUR_QUEUE",
              "Condition": {
                "ArnLike": {
                  "aws:SourceArn": "CHANGE_TO_ARN_FOR_YOUR_BUCKET"
                }
              }
            }
          ]
        }

   .. note::
       change the CHANGE_TO_UNIQUE_ID values for "Id" and "Sid" to reflect unique identifiers. You must also replace the CHANGE_TO_ARN_FOR_YOUR_QUEUE & CHANGE_TO_ARN_FOR_YOUR_BUCKET with the arns to your queue and to your s3 bucket respectively
#. click "Review Policy"
#. click "Save Changes"

s3 configuration
================
#. navigate back to the s3 page
#. click on your s3 bucket
#. select the "Permissions" tab
#. select "Bucket Policy"
#. replace the contents of the text editor with the following:

   .. code-block:: json

       {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "CHANGE_TO_UNIQUE_ID",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "cloudtrail.amazonaws.com"
                    },
                    "Action": "s3:GetBucketAcl",
                    "Resource": "CHANGE_TO_ARN_FOR_YOUR_BUCKET"
                },
                {
                    "Sid": "CHANGE_TO_UNIQUE_ID",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "cloudtrail.amazonaws.com"
                    },
                    "Action": "s3:PutObject",
                    "Resource": [
                        "CHANGE_TO_ARN_FOR_YOUR_BUCKET/AWSLogs/*"
                    ],
                    "Condition": {
                        "StringEquals": {
                            "s3:x-amz-acl": "bucket-owner-full-control"
                        }
                    }
                }
            ]
        }
   .. note::
       change the CHANGE_TO_UNIQUE_ID values for "Id" and "Sid" to reflect unique identifiers. You must also replace CHANGE_TO_ARN_FOR_YOUR_BUCKET with your bucket arn.
#. click "Save"
#. navigate to the "Policies" tab
#. scroll down to the Advanced settings
#. select Events
#. click on "Add notification"
    - supply a unique name
    - select the "ObjectCreate (All)" option under Events
    - set the prefix to "AWSLogs"
    - set the suffix to ".json.gz"
    - select "SQS Queue" as the notification destination under "Send to"
    - select your queue under SQS
#. click "Save"

Adding your S3 bucket environment variable
==========================================
#. you must provide your bucket name to cloudigrade
#. ``export S3_BUCKET_NAME=your-bucket-name``
