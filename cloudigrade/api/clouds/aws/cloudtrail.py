"""Functions for parsing relevant data from CloudTrail messages."""
CREATE_TAG = "CreateTags"
DELETE_TAG = "DeleteTags"
ec2_ami_tag_event_list = [CREATE_TAG, DELETE_TAG]
