import base64
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

# Force bogus values into required environment variables.
os.environ["CLOUDIGRADE_ENVIRONMENT"] = "rest-api-examples"
os.environ["AWS_ACCESS_KEY_ID"] = "nope"
os.environ["AWS_SECRET_ACCESS_KEY"] = "nope"
os.environ["AWS_DEFAULT_REGION"] = "nope"
os.environ["AZURE_CLIENT_ID"] = "f5daa17f-exam-ple3-8d70-8f7f301b1466"
os.environ["AZURE_CLIENT_SECRET"] = "nope"
os.environ["AZURE_SP_OBJECT_ID"] = "691f0b3e-exam-ple3-b03f-6eb5120acabb"
os.environ["AZURE_SUBSCRIPTION"] = "62c769b6-exam-ple3-ba22-d272720a649e"
os.environ["AZURE_TENANT_ID"] = "81329282-exam-ple3-80af-f6457b5b32ad"

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
from django.conf import settings

from api.models import User
from api import models
from api.tests import helper as api_helper
from api.util import calculate_max_concurrent_usage, denormalize_runs
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
    ), f"{response} should have status {status_code}; {response.data}"


class DocsApiHandler(object):
    """Handle API calls with lots of custom data setup and helper clients."""

    def __init__(self):
        """Initialize all the data for the examples."""
        api_helper.generate_instance_type_definitions(cloud_type="aws")
        api_helper.generate_instance_type_definitions(cloud_type="azure")

        self.customer_account_number = "100001"
        self.customer_user = util_helper.get_test_user(
            self.customer_account_number, is_superuser=False
        )
        self.customer_user.date_joined = util_helper.utc_dt(2019, 1, 1, 0, 0, 0)
        self.customer_user.save()

        self.x_rh_identity = util_helper.get_identity_auth_header(
            self.customer_account_number
        ).decode("utf-8")

        # Create the fake HTTP clients
        # Anonymous client has no authentication.
        self.anonymous_client = api_helper.SandboxedRestClient()
        # Customer client has its user and identity header ready for all requests.
        self.customer_client = api_helper.SandboxedRestClient()
        self.customer_client._force_authenticate(
            self.customer_user, {"HTTP_X_RH_IDENTITY": self.x_rh_identity}
        )
        # Internal client has its user and identity header ready for all requests.
        self.internal_client = api_helper.SandboxedRestClient(
            api_root="/internal/api/cloudigrade/v1"
        )
        self.internal_client._force_authenticate(
            self.customer_user, {"HTTP_X_RH_IDENTITY": self.x_rh_identity}
        )
        # Another internal client has its user but no default identity header.
        # Manually set other x-rh-cloudigrade-* headers on individual requests.
        self.internal_client_no_rh_identity = api_helper.SandboxedRestClient(
            api_root="/internal/api/cloudigrade/v1"
        )
        self.internal_client._force_authenticate(self.customer_user)

        self.customer_arn = util_helper.generate_dummy_arn()

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
        self.aws_customer_account = api_helper.generate_cloud_account_aws(
            arn=util_helper.generate_dummy_arn(),
            user=self.customer_user,
            created_at=self.two_weeks_ago,
        )
        self.azure_customer_account = api_helper.generate_cloud_account_azure(
            user=self.customer_user,
            created_at=self.two_weeks_ago,
            azure_subscription_id=str(seeded_uuid4()),
        )
        self.customer_instances = [
            api_helper.generate_instance(self.aws_customer_account),
            api_helper.generate_instance(self.aws_customer_account),
            api_helper.generate_instance(self.aws_customer_account),
            api_helper.generate_instance(self.azure_customer_account),
            api_helper.generate_instance(self.azure_customer_account),
            api_helper.generate_instance(self.azure_customer_account),
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
        denormalized_runs = denormalize_runs(models.InstanceEvent.objects.all())
        for denormalized_run in denormalized_runs:
            run = models.Run(
                start_time=denormalized_run.start_time,
                end_time=denormalized_run.end_time,
                machineimage_id=denormalized_run.image_id,
                instance_id=denormalized_run.instance_id,
                instance_type=denormalized_run.instance_type,
                memory=denormalized_run.instance_memory,
                vcpu=denormalized_run.instance_vcpu,
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
        responses["v2_rh_identity"] = json.loads(
            base64.b64decode(self.x_rh_identity.encode("utf-8")).decode("utf-8")
        )
        # convert from binary string to string.
        responses["v2_header"] = self.x_rh_identity

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
                "start_date": self.yesterday.date(),
                "end_date": self.next_week.date(),
            }
        )
        assert_status(response, 400)
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
        assert_status(response, 400)
        responses["v2_list_concurrent_all_future"] = response

        response = self.customer_client.list_concurrent(
            data={
                "start_date": self.customer_user.date_joined - timedelta(days=14),
                "end_date": self.customer_user.date_joined - timedelta(days=7),
            }
        )
        assert_status(response, 400)
        responses["v2_list_concurrent_past_end_date"] = response

        ##########################
        # v2 Customer Account Info

        # List all accounts
        response = self.customer_client.list_accounts()
        assert_status(response, 200)
        responses["v2_account_list"] = response

        # Retrieve a specific account
        response = self.customer_client.get_accounts(self.aws_customer_account.id)
        assert_status(response, 200)
        responses["v2_account_get"] = response

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

    def gather_internal_api_responses(self):
        """
        Call the internal API and collect all the responses to be output.

        Returns:
            dict: All of the internal API responses.

        """
        responses = dict()

        _faker = faker.Faker()

        psk = str(_faker.uuid4())
        account_number = str(_faker.random_int(min=10000, max=999999))
        org_id = str(_faker.random_int(min=10000, max=999999))

        responses["internal_psk"] = psk
        responses["internal_account_number"] = account_number
        responses["internal_org_id"] = org_id

        ############################
        # Internal Customer Account Setup AWS

        # Create an AWS account (success)
        another_arn = util_helper.generate_dummy_arn()
        aws_cloud_account_data = (
            util_helper.generate_dummy_aws_cloud_account_post_data()
        )
        aws_cloud_account_data.update({"account_arn": another_arn})
        response = self.internal_client.create_accounts(data=aws_cloud_account_data)
        assert_status(response, 201)
        responses["internal_account_create_aws"] = response

        customer_account = models.CloudAccount.objects.get(
            id=response.data["account_id"]
        )

        # Create an AWS account (fail: duplicate ARN)
        aws_cloud_account_duplicate_arn_data = (
            util_helper.generate_dummy_aws_cloud_account_post_data()
        )
        aws_cloud_account_duplicate_arn_data.update({"account_arn": another_arn})
        response = self.internal_client.create_accounts(
            data=aws_cloud_account_duplicate_arn_data
        )
        assert_status(response, 400)
        responses["internal_account_create_aws_duplicate_arn"] = response

        # Create an Azure account (success)
        subscription_id = str(seeded_uuid4())
        azure_cloud_account_data = (
            util_helper.generate_dummy_azure_cloud_account_post_data()
        )
        azure_cloud_account_data.update({"subscription_id": subscription_id})
        response = self.internal_client.create_accounts(data=azure_cloud_account_data)
        assert_status(response, 201)
        responses["internal_account_create_azure"] = response

        # List users filtered to specific account_number
        # using another custom X-RH- header, not the typical X-RH-IDENTITY.
        with override_settings(CLOUDIGRADE_PSKS={"docs": psk}):
            response = self.internal_client_no_rh_identity.get_users(
                data={"account_number": self.customer_user.account_number},
                HTTP_X_RH_CLOUDIGRADE_PSK=psk,
            )
        assert_status(response, 200)
        responses["internal_user_list_filtered_by_account_number"] = response

        return responses

    def gather_anonymous_api_responses(self):
        """
        Call the public API and collect all the responses to be output.

        Returns:
            dict: All of the API responses.

        """
        responses = dict()

        ########################
        # V2 Public Commands
        # Retrieve the ARM Offer Template
        response = self.anonymous_client.verb_noun(
            verb="get", noun="azure-offer-template"
        )
        assert_status(response, 200)
        responses["v2_get_azure_offer"] = response

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
    ), patch.object(uuid, "uuid4") as mock_uuid4, patch(
        "api.tasks.sources.notify_application_availability_task"
    ) as mock_notify_sources, patch(
        "api.clouds.azure.models.AzureCloudAccount.enable"
    ) as mock_azure_enable, util_helper.clouditardis(
        docs_date
    ):
        mock_uuid4.side_effect = seeded_uuid4
        mock_azure_enable.return_value = True
        api_handler = DocsApiHandler()
        authenticated_responses = api_handler.gather_api_responses()
        internal_responses = api_handler.gather_internal_api_responses()
        anonymous_responses = api_handler.gather_anonymous_api_responses()
        transaction.set_rollback(True)
    all_responses = {}
    all_responses.update(authenticated_responses)
    all_responses.update(internal_responses)
    all_responses.update(anonymous_responses)
    output = render(all_responses)
    output = "\n".join((line.rstrip() for line in output.split("\n")))
    print(output)
