import json
import os
import random
import uuid
from datetime import timedelta
from unittest.mock import patch

import django
import faker
import jinja2
from django.core.management import call_command
from django.core.management.commands import migrate
from django.db import transaction
from django.test import override_settings

# Force this script to always use the test settings.
# This has the benefit of using the sqlite DB which should always be empty.
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
# However, this means we also need to apply migrations for that DB.
migrate_cmd = migrate.Command()
call_command(migrate_cmd, verbosity=0, interactive=False)
# Run setup only *after* applying migrations.
django.setup()

# All other app-related imports must come *after* Django setup since this is
# a standalone script.
from django.contrib.auth.models import User
from django.conf import settings

from api import models
from api.clouds.aws.models import AwsCloudAccount
from api.tests import helper as api_helper
from api.util import calculate_max_concurrent_usage, normalize_runs
from util import filters
from util.misc import get_now
from util.tests import helper as util_helper


def empty_check():
    """Assert there are no users before starting."""
    users_count = User.objects.count()
    assert users_count == 0, (
        f"Found {users_count} users, but your database should be empty.\n"
        f"Consider using this command to reset your database:\n\n"
        f"  manage.py sqlflush | psql -h localhost -U postgres"
    )


def assert_status(response, status_code):
    """Assert the response has the expected status code."""
    assert (
        response.status_code == status_code
    ), f"{response} should have status {status_code}"


class DocsApiHandler(object):
    """Handle API calls with lots of custom data setup and helper clients."""

    def __init__(self):
        """Initialize all the data for the examples."""
        api_helper.generate_instance_type_definitions(cloud_type="aws")
        api_helper.generate_instance_type_definitions(cloud_type="azure")

        self.superuser_account_number = "100000"
        self.superuser = util_helper.get_test_user(
            self.superuser_account_number, is_superuser=True
        )
        self.superuser_client = api_helper.SandboxedRestClient()
        self.superuser_client._force_authenticate(self.superuser)

        self.customer_account_number = f"100001"
        self.customer_password = "very-secure-password"
        self.customer_user = util_helper.get_test_user(
            self.customer_account_number, self.customer_password, is_superuser=False
        )
        self.customer_client = api_helper.SandboxedRestClient()
        self.customer_client._force_authenticate(self.customer_user)

        self.customer_arn = util_helper.generate_dummy_arn()

        # Make sure an account doesn't already exist with that ARN.
        for account in AwsCloudAccount.objects.filter(account_arn=self.customer_arn):
            self.superuser_client.delete_account(account.id)

        # Times to use for various account and event activity.
        self.now = get_now()
        self.this_morning = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.yesterday = self.this_morning - timedelta(days=1)
        self.last_month = self.this_morning - timedelta(days=31)
        self.last_week = self.this_morning - timedelta(days=7)
        self.three_days_ago = self.this_morning - timedelta(days=3)
        self.two_days_ago = self.this_morning - timedelta(days=2)
        self.two_weeks_ago = self.this_morning - timedelta(weeks=2)
        self.tomorrow = self.this_morning + timedelta(days=1)
        self.next_week = self.this_morning + timedelta(weeks=1)

        ######################################
        # Generate AWS data for the customer user.
        self.aws_customer_account = api_helper.generate_cloud_account(
            arn=util_helper.generate_dummy_arn(),
            user=self.customer_user,
            name="greatest account ever",
            created_at=self.two_weeks_ago,
        )
        self.azure_customer_account = api_helper.generate_cloud_account(
            user=self.customer_user,
            name="meh account",
            created_at=self.two_weeks_ago,
            cloud_type="azure",
            azure_subscription_id=str(seeded_uuid4()),
            azure_tenant_id=str(seeded_uuid4()),
        )
        self.customer_instances = [
            api_helper.generate_instance(self.aws_customer_account),
            api_helper.generate_instance(self.aws_customer_account),
            api_helper.generate_instance(self.aws_customer_account),
            api_helper.generate_instance(
                self.azure_customer_account, cloud_type="azure"
            ),
            api_helper.generate_instance(
                self.azure_customer_account, cloud_type="azure"
            ),
            api_helper.generate_instance(
                self.azure_customer_account, cloud_type="azure"
            ),
        ]

        # Generate events so we can see customer activity in the responses.
        # These events represent all customer instances starting one week ago,
        # stopping two days ago, and starting again yesterday.
        self.events = []
        for instance in self.customer_instances[:2]:
            self.events.extend(
                api_helper.generate_instance_events(
                    instance,
                    [
                        (self.last_week, self.three_days_ago),
                        (self.yesterday, None),
                    ],
                )
            )
        for instance in self.customer_instances[3:6]:
            self.events.extend(
                api_helper.generate_instance_events(
                    instance,
                    [
                        (self.last_week, self.three_days_ago),
                        (self.yesterday, None),
                    ],
                    cloud_type="azure",
                )
            )

        # Build the runs for the created events.
        # Note: this crude and *direct* implementation of Run-saving should be
        # replaced as we continue porting pilot functionality and (eventually)
        # better general-purpose Run-handling functions materialize.
        normalized_runs = normalize_runs(models.InstanceEvent.objects.all())
        for normalized_run in normalized_runs:
            run = models.Run(
                start_time=normalized_run.start_time,
                end_time=normalized_run.end_time,
                machineimage_id=normalized_run.image_id,
                instance_id=normalized_run.instance_id,
                instance_type=normalized_run.instance_type,
                memory=normalized_run.instance_memory,
                vcpu=normalized_run.instance_vcpu,
            )
            run.save()

        # Force all images to have RHEL detected ("7.7")
        self.images = list(
            set(
                instance.machine_image
                for instance in self.customer_instances
                if instance.machine_image is not None
            )
        )
        for image in self.images:
            image.inspection_json = json.dumps(
                {
                    "rhel_enabled_repos_found": True,
                    "rhel_version": "7.7",
                    "syspurpose": {
                        "role": "Red Hat Enterprise Linux Server",
                        "service_level_agreement": "Premium",
                        "usage": "Development/Test",
                    },
                }
            )
            image.status = image.INSPECTED
            image.region = "us-east-1"
            image.save()

        # Pre-calculate concurrent usage data for upcoming requests.
        # Calculate each day since "last week" (oldest date we use in example requests).
        the_date = self.last_week.date()
        one_day_delta = timedelta(days=1)
        # while the_date <= self.this_morning.date():
        while the_date <= self.next_week.date():
            task_id = f"calculate-concurrent-usage-{seeded_uuid4()}"
            models.ConcurrentUsageCalculationTask.objects.create(
                user_id=self.customer_user.id,
                date=the_date.isoformat(),
                task_id=task_id,
                status=models.ConcurrentUsageCalculationTask.COMPLETE,
            )
            calculate_max_concurrent_usage(the_date, self.customer_user.id)
            the_date = the_date + one_day_delta

    def gather_api_responses(self):
        """
        Call the API and collect all the responses to be output.

        Returns:
            dict: All of the API responses.

        """
        responses = dict()

        ########################
        # V2 endpoints
        responses["v2_rh_identity"] = util_helper.RH_IDENTITY_ORG_ADMIN
        # convert from binary string to string.
        responses["v2_header"] = util_helper.get_3scale_auth_header().decode("utf-8")

        #######################
        # Report Commands
        # IMPORTANT NOTE!
        # These requests must come FIRST since they rely on calculated concurrent usage
        # data that might be clobbered by other subsequent operations.

        # Daily Max Concurrency
        response = self.customer_client.list_concurrent(
            data={"start_date": self.last_week.date()}
        )
        assert_status(response, 200)
        responses["v2_list_concurrent"] = response

        response = self.customer_client.list_concurrent(
            data={
                "start_date": self.this_morning.date(),
                "end_date": self.next_week.date(),
            }
        )
        assert_status(response, 200)
        responses["v2_list_concurrent_partial_future"] = response

        response = self.customer_client.list_concurrent(
            data={"start_date": self.last_month.date()}
        )
        assert_status(response, 425)
        responses["v2_list_concurrent_too_early"] = response
        # IMPORTANT NOTE FOR THIS SCRIPT!
        # Because that request raised a 425 and would *normally* trigger a rollback,
        # we need to squash that rollback here and let the transaction continue.
        transaction.set_rollback(False)

        response = self.customer_client.list_concurrent(
            data={
                "start_date": self.tomorrow.date(),
                "end_date": self.next_week.date(),
            }
        )
        assert_status(response, 200)
        responses["v2_list_concurrent_all_future"] = response

        ############################
        # Customer Account Setup AWS

        # Create an AWS account (success)
        another_arn = util_helper.generate_dummy_arn()
        aws_cloud_account_data = (
            util_helper.generate_dummy_aws_cloud_account_post_data()
        )
        aws_cloud_account_data.update(
            {"account_arn": another_arn, "name": "yet another account"}
        )
        response = self.customer_client.create_accounts(data=aws_cloud_account_data)
        assert_status(response, 201)
        responses["v2_account_create"] = response

        customer_account = models.CloudAccount.objects.get(
            id=response.data["account_id"]
        )

        # Create an AWS account (fail: duplicate ARN)
        aws_cloud_account_duplicate_arn_data = (
            util_helper.generate_dummy_aws_cloud_account_post_data()
        )
        aws_cloud_account_duplicate_arn_data.update(
            {"account_arn": another_arn, "name": "but this account already exists"}
        )
        response = self.customer_client.create_accounts(
            data=aws_cloud_account_duplicate_arn_data
        )
        assert_status(response, 400)
        responses["v2_account_create_duplicate_arn"] = response

        ##############################
        # Customer Account Setup Azure

        # Create an Azure account (success)
        tenant_id = uuid.uuid4()
        azure_cloud_account_data = (
            util_helper.generate_dummy_azure_cloud_account_post_data()
        )
        azure_cloud_account_data.update(
            {"tenant_id": tenant_id, "name": "it's an azure account"}
        )
        response = self.customer_client.create_accounts(data=azure_cloud_account_data)
        assert_status(response, 201)
        responses["v2_account_create_azure"] = response

        ##########################
        # v2 Customer Account Info

        # List all accounts
        response = self.customer_client.list_accounts()
        assert_status(response, 200)
        responses["v2_account_list"] = response

        # Retrieve a specific account
        response = self.customer_client.get_accounts(customer_account.id)
        assert_status(response, 200)
        responses["v2_account_get"] = response

        # Update a specific account
        response = self.customer_client.patch_accounts(
            customer_account.id, data={"name": "name updated using PATCH"}
        )
        assert_status(response, 200)
        responses["v2_account_patch"] = response

        aws_cloud_account_put_different_name_data = aws_cloud_account_data.copy()
        aws_cloud_account_put_different_name_data.update(
            {"name": "name updated using PUT"}
        )
        response = self.customer_client.put_accounts(
            customer_account.id,
            data=aws_cloud_account_put_different_name_data,
        )
        assert_status(response, 200)
        responses["v2_account_put"] = response

        # You cannot change the ARN via PUT or PATCH.
        response = self.customer_client.patch_accounts(
            customer_account.id,
            data={"account_arn": "arn:aws:iam::999999999999:role/role-for-cloudigrade"},
        )
        assert_status(response, 400)
        responses["v2_account_patch_arn_fail"] = response

        ##################
        # V2 Instance Info

        # List all instances
        response = self.customer_client.list_instances()
        assert_status(response, 200)
        responses["v2_instance_list"] = response

        # Retrieve a specific instance
        response = self.customer_client.get_instances(self.customer_instances[0].id)
        assert_status(response, 200)
        responses["v2_instance_get"] = response

        # Filtering instances on running
        response = self.customer_client.list_instances(data={"running_since": self.now})
        assert_status(response, 200)
        responses["v2_instance_filter_running"] = response

        #######################
        # V2 Machine Image Info

        # List all images
        response = self.customer_client.list_images()
        assert_status(response, 200)
        responses["v2_list_images"] = response

        # Retrieve a specific image
        response = self.customer_client.get_images(self.images[0].id)
        assert_status(response, 200)
        responses["v2_get_image"] = response

        ########################
        # V2 Miscellaneous Commands
        # Retrieve current cloud account ids used by the application
        cloudigrade_version = (
            "489-cloudigrade-version - " "d2b30c637ce3788e22990b21434bac2edcfb7ede"
        )

        with override_settings(CLOUDIGRADE_VERSION=cloudigrade_version):
            response = self.customer_client.get_sysconfig()
        assert_status(response, 200)
        responses["v2_get_sysconfig"] = response

        return responses


def render(data):
    """
    Render the document with the given API responses.

    Args:
        data(dict): the data to feed into the template for rendering

    Note:
        This treats the this script's parent directory as the template
        environment root so it can find the jinja template.

    Returns:
        string: The rendered document.

    """
    loader = jinja2.FileSystemLoader(os.path.join(settings.ROOT_DIR, "..", "docs"))
    env = jinja2.Environment(autoescape=False, loader=loader)

    env.filters["rst_codeblock"] = filters.rst_codeblock
    env.filters["stringify_http_response"] = filters.stringify_http_response
    env.filters["httpied_command"] = filters.httpied_command
    template = env.get_template("rest-api-examples.rst.jinja")
    return template.render(**data)


def seeded_uuid4():
    """Generate uuid4 using insecure random so we can control its seed."""
    return uuid.UUID(bytes=bytes([random.getrandbits(8) for _ in range(16)]), version=4)


if __name__ == "__main__":
    empty_check()
    # Reset random seeds for more consistent output.
    random.seed(0)
    faker.Faker.seed(0)
    docs_date = util_helper.utc_dt(2020, 5, 18, 13, 51, 59, 722367)
    with transaction.atomic(), override_settings(
        SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False
    ), patch.object(uuid, "uuid4") as mock_uuid4, util_helper.clouditardis(docs_date):
        mock_uuid4.side_effect = seeded_uuid4
        api_hander = DocsApiHandler()
        responses = api_hander.gather_api_responses()
        transaction.set_rollback(True)
    output = render(responses)
    output = "\n".join((line.rstrip() for line in output.split("\n")))
    print(output)
