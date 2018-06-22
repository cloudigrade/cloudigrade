***********************************
AWS S3 and SQS setup for CloudTrail
***********************************

S3 Setup
========
1. log in to the AWS web console for your cluster account
1. go to the s3 (Simple Storage Service) page
1. click "Create bucket"
1. enter a unique name for your bucket ("yourname-cloudigrade-s3")
1. select a region (us-east-1) and click "Next"
1. the default properties and permissions are OK, click "Next" until you reach the "Review" step
1. click "Create bucket"

SQS setup
=========
1. navigate to the SQS (Simple Queue Service) page
1. click "Create New Queue"
1. Give the queue a reasonably unique name ("yourname-cloudigrade-sqs")
1. select Standard Queue and click "Quick-Create Queue"
1. select your queue and click on the "Permissions" tab
1. select "Edit Policy Document (Advanced)"
1. Click JSON to switch to the text editor.
1. Replace the contents of the text editor with the following:

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
1. click "Review Policy"
1. click "Save Changes"

s3 configuration
================
1. navigate back to the s3 page
1. click on your s3 bucket
1. select the "Permissions" tab
1. select "Bucket Policy"
1. Replace the contents of the text editor with the following:

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
1. click "Save"
1. Navigate to the "Policies" tab
1. Scroll down to the Advanced settings
1. Select Events
1. Click on "Add notification"
    - supply a unique name
    - select the "ObjectCreate (All)" option under Events
    - set the prefix to "AWSLogs"
    - set the suffix to ".json.gz"
    - select "SQS Queue" as the notification destination under "Send to"
    - select your queue under SQS
1. click "Save"

Adding your S3 bucket environment variable
==========================================
1. you must provide your bucket name to cloudigrade
1. ``export S3_BUCKET_NAME=your-bucket-name``
