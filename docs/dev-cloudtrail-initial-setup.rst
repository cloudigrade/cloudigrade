***********************************
AWS S3 and SQS setup for CloudTrail
***********************************

S3 setup
========
#. log in to the AWS web console for your cluster account
#. go to the s3 (Simple Storage Service) page
#. click "Create bucket"
#. enter a unique name for your bucket ("yourname-cloudigrade-s3")
#. select a region (us-east-1) and click "Next"
#. the default properties and permissions are OK, click "Next" until you reach the "Review" step
#. click "Create bucket"

SQS setup
=========
#. navigate to the SQS (Simple Queue Service) page
#. click "Create New Queue"
#. give the queue a reasonably unique name ("yourname-cloudigrade-sqs")
#. select Standard Queue and click "Quick-Create Queue"
#. select your queue and click on the "Permissions" tab
#. select "Edit Policy Document (Advanced)"
#. click JSON to switch to the text editor.
#. replace the contents of the text editor with the following:

   .. code-block:: json

       {
          "Version": "2012-10-17",
          "Id": "unique-identifier",
          "Statement": [
            {
              "Sid": "unique-identifier",
              "Effect": "Allow",
              "Principal": {
                "AWS": "*"
              },
              "Action": "SQS:SendMessage",
              "Resource": "arn-for-your-queue",
              "Condition": {
                "ArnLike": {
                  "aws:SourceArn": "arn-for-your-bucket"
                }
              }
            }
          ]
        }

   .. note::
       change the "Id" and "Sid" values to reflect unique identifiers. You must also replace the resource arns with the arns to your queue and to your s3 bucket respectively
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
                    "Sid": "unique-id",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "cloudtrail.amazonaws.com"
                    },
                    "Action": "s3:GetBucketAcl",
                    "Resource": "arn-for-your-bucket"
                },
                {
                    "Sid": "unique-id",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "cloudtrail.amazonaws.com"
                    },
                    "Action": "s3:PutObject",
                    "Resource": [
                        "arn-for-your-bucket/AWSLogs/*"
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
       change the "Id" and "Sid" values to reflect unique identifiers. You must also replace the resource arns with your bucket arn
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
