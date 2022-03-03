"""Helper utility module to wrap up common AWS ARN operations."""
import re
from decimal import Decimal

from util.exceptions import InvalidArn


class AwsArn(object):
    """
    Object representing an AWS ARN.

    See also:
        https://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html

    General ARN formats:
        arn:partition:service:region:account-id:resource
        arn:partition:service:region:account-id:resourcetype/resource
        arn:partition:service:region:account-id:resourcetype:resource

    Example ARNs:
        <!-- Elastic Beanstalk application version -->
        arn:aws:elasticbeanstalk:us-east-1:123456789012:environment/My App/foo

        <!-- IAM user name -->
        arn:aws:iam::123456789012:user/David

        <!-- Amazon RDS instance used for tagging -->
        arn:aws:rds:eu-west-1:123456789012:db:mysql-db

        <!-- Object in an Amazon S3 bucket -->
        arn:aws:s3:::my_corporate_bucket/exampleobject.png

    """

    arn_regex = re.compile(
        r"^arn:(?P<partition>\w+(?:-\w+)*):(?P<service>\w+):"
        r"(?P<region>\w+(?:-\w+)+)?:"
        r"(?P<account_id>\d{1,12})?:"
        r"(?P<resource_type>[^:/]+)"
        r"(?P<resource_separator>[:/])?(?P<resource>.*)"
    )

    partition = None
    service = None
    region = None
    account_id = None
    resource_type = None
    resource_separator = None
    resource = None

    def __init__(self, arn):
        """
        Parse ARN string into its component pieces.

        Args:
            arn (str): Amazon Resource Name

        """
        self.arn = arn
        match = self.arn_regex.match(arn)

        if not match:
            raise InvalidArn("Invalid ARN: {0}".format(arn))

        for key, val in match.groupdict().items():
            if key == "account_id":
                try:
                    val = Decimal(val)
                except TypeError:
                    raise InvalidArn("Invalid ARN account ID: {0} {1}".format(arn, val))
            setattr(self, key, val)

    def __repr__(self):
        """Return the ARN itself."""
        return self.arn
