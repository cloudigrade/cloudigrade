import json
import os
from datetime import datetime, timedelta

import django
import jinja2
from dateutil import tz
from django.test import override_settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

# All other app-related imports must come *after* Django setup since this is
# a standalone script.
from django.contrib.auth.models import User
from django.conf import settings

from util.tests.helper import get_test_user
from util import filters

from account import models
from account.tests import helper as account_helper
from util.tests import helper as util_helper


def empty_check():
    """Assert there are no users before starting."""
    users_count = User.objects.count()
    assert users_count == 0, (
        f'Found {users_count} users, but your database should be empty.\n'
        f'Consider using this command to reset your database:\n\n'
        f'  manage.py sqlflush | psql -h localhost -U postgres'
    )


def assert_status(response, status_code):
    """Assert the response has the expected status code."""
    assert (
        response.status_code == status_code
    ), f'{response} should have status {status_code}'


class DocsApiHandler(object):
    """Handle API calls with lots of custom data setup and helper clients."""

    def __init__(self):
        """Initialize all the data for the examples."""
        self.superuser_email = f'superuser@example.com'
        self.superuser = get_test_user(self.superuser_email, is_superuser=True)
        self.superuser_client = account_helper.SandboxedRestClient()
        self.superuser_client._force_authenticate(self.superuser)

        self.customer_email = f'customer@example.com'
        self.customer_password = 'very-secure-password'
        self.customer_user = get_test_user(
            self.customer_email, self.customer_password, is_superuser=False
        )
        self.customer_client = account_helper.SandboxedRestClient()
        self.customer_arn = util_helper.generate_dummy_arn()

        # Make sure an account doesn't already exist with that ARN.
        for account in models.AwsAccount.objects.filter(
            account_arn=self.customer_arn
        ):
            self.superuser_client.delete_account(account.id)

        # Times to use for various account and event activity.
        self.now = datetime.now(tz=tz.tzutc())
        self.this_morning = self.now.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self.yesterday = self.this_morning - timedelta(days=1)
        self.last_week = self.this_morning - timedelta(days=7)
        self.three_days_ago = self.this_morning - timedelta(days=3)
        self.two_days_ago = self.this_morning - timedelta(days=2)
        self.two_weeks_ago = self.this_morning - timedelta(weeks=2)

        ##################################
        # Generate data for the superuser.
        self.superuser_account = account_helper.generate_aws_account(
            arn=util_helper.generate_dummy_arn(),
            user=self.superuser,
            name='super duper account',
            created_at=self.two_weeks_ago,
        )
        self.superuser_instances = [
            account_helper.generate_aws_instance(self.superuser_account)
        ]

        self.events = []
        # This event represents one instance starting yesterday.
        self.events.extend(
            account_helper.generate_aws_instance_events(
                self.superuser_instances[0], [(self.yesterday, None)]
            )
        )

        ######################################
        # Generate data for the customer user.
        self.customer_account = account_helper.generate_aws_account(
            arn=util_helper.generate_dummy_arn(),
            user=self.customer_user,
            name='greatest account ever',
            created_at=self.two_weeks_ago,
        )
        self.customer_instances = [
            account_helper.generate_aws_instance(self.customer_account),
            account_helper.generate_aws_instance(self.customer_account),
            account_helper.generate_aws_instance(self.customer_account),
        ]

        # Generate events so we can see customer activity in the responses.
        # These events represent all customer instances starting one week ago,
        # stopping two days ago, and starting again yesterday.
        for instance in self.customer_instances[:2]:
            self.events.extend(
                account_helper.generate_aws_instance_events(
                    instance,
                    [
                        (self.last_week, self.two_days_ago),
                        (self.yesterday, None),
                    ],
                )
            )

        # Force all images to have RHEL detected and OCP challenged.
        self.images = list(
            set(
                event.machineimage
                for event in self.events
                if event.machineimage is not None
            )
        )
        for image in self.images:
            image.inspection_json = json.dumps(
                {'rhel_enabled_repos_found': True}
            )
            image.openshift_challenged = True
            image.status = image.INSPECTED
            image.region = 'us-east-1'
            image.save()

    def cleanup(self):
        """Delete everything we created here."""
        for account in models.AwsAccount.objects.all():
            self.superuser_client.delete_account(account.id)
        models.MachineImage.objects.all().delete()
        User.objects.all().delete()

    def gather_api_responses(self):
        """
        Call the API and collect all the responses to be output.

        Returns:
            dict: All of the API responses.

        """
        responses = dict()

        ############
        # User Setup

        # Login to Cloudigrade
        response = self.customer_client.login(
            self.customer_email, self.customer_password
        )
        assert_status(response, 200)
        responses['login'] = response

        # Log out of Cloudigrade
        response = self.customer_client.logout()
        assert_status(response, 204)
        responses['logout'] = response

        # ...but actually log in again so we can make more API calls later...
        self.customer_client.login(self.customer_email, self.customer_password)

        ########################
        # Customer Account Setup

        # Create an AWS account (success)
        another_arn = util_helper.generate_dummy_arn()
        response = self.customer_client.create_account(
            data={
                'account_arn': another_arn,
                'name': 'yet another account',
                'resourcetype': 'AwsAccount',
            }
        )
        assert_status(response, 201)
        responses['account_create'] = response

        customer_account = models.AwsAccount.objects.get(
            account_arn=another_arn
        )

        # Create an AWS account (fail: duplicate ARN)
        response = self.customer_client.create_account(
            data={
                'account_arn': another_arn,
                'name': 'but this account already exists',
                'resourcetype': 'AwsAccount',
            }
        )
        assert_status(response, 400)
        responses['account_create_duplicate_arn'] = response

        #######################
        # Customer Account Info

        # List all accounts
        response = self.customer_client.list_account()
        assert_status(response, 200)
        responses['account_list'] = response

        # Retrieve a specific account
        response = self.customer_client.get_account(customer_account.id)
        assert_status(response, 200)
        responses['account_get'] = response

        # Update a specific account
        response = self.customer_client.patch_account(
            customer_account.id,
            data={
                'name': 'name updated using PATCH',
                'resourcetype': 'AwsAccount',
            },
        )
        assert_status(response, 200)
        responses['account_patch'] = response

        response = self.customer_client.put_account(
            customer_account.id,
            data={
                'name': 'name updated using PUT',
                'account_arn': another_arn,
                'resourcetype': 'AwsAccount',
            },
        )
        assert_status(response, 200)
        responses['account_put'] = response

        # You cannot change the ARN via PUT or PATCH.
        response = self.customer_client.patch_account(
            customer_account.id,
            data={
                'account_arn': 'arn:aws:iam::999999999999:role/role-for-cloudigrade',
                'resourcetype': 'AwsAccount',
            },
        )
        assert_status(response, 400)
        responses['account_patch_arn_fail'] = response

        ###############
        # Instance Info

        # List all instances
        response = self.customer_client.list_instance()
        assert_status(response, 200)
        responses['instance_list'] = response

        # Retrieve a specific instance
        response = self.customer_client.get_instance(
            self.customer_instances[0].id
        )
        assert_status(response, 200)
        responses['instance_get'] = response

        # Filtering instances
        response = self.superuser_client.list_instance(
            data={'user_id': self.superuser.id}
        )
        assert_status(response, 200)
        responses['instance_filter'] = response

        #####################
        # Instance Event Info

        # List all events
        response = self.customer_client.list_event()
        assert_status(response, 200)
        responses['event_list'] = response

        # Retrieve a specific instance
        response = self.customer_client.get_event(
            responses['event_list'].json()['results'][0]['id']
        )
        assert_status(response, 200)
        responses['event_get'] = response

        response = self.customer_client.list_event(
            data={'instance_id': self.customer_instances[0].id}
        )
        assert_status(response, 200)
        responses['event_filter_instance'] = response

        response = self.superuser_client.list_event(
            data={'user_id': self.superuser.id}
        )
        assert_status(response, 200)
        responses['event_filter_user'] = response

        # Retrieve a daily instance usage report
        response = self.customer_client.report_instances(
            data={'start': self.three_days_ago, 'end': self.this_morning}
        )
        assert_status(response, 200)
        responses['report_instances'] = response

        # Retrieve an account overview
        response = self.customer_client.report_accounts(
            data={'start': self.three_days_ago, 'end': self.this_morning}
        )
        assert_status(response, 200)
        responses['report_accounts'] = response

        response = self.customer_client.report_accounts()
        assert_status(response, 400)
        responses['report_accounts_no_args'] = response

        response = self.customer_client.report_accounts(
            data={
                'start': self.three_days_ago,
                'end': self.this_morning,
                'name_pattern': 'eat tofu',
            }
        )
        assert_status(response, 200)
        responses['report_accounts_filter'] = response

        # Retrieve an account's active images overview
        response = self.customer_client.report_images(
            data={
                'start': self.three_days_ago,
                'end': self.this_morning,
                'account_id': self.customer_account.id,
            }
        )
        assert_status(response, 200)
        responses['report_images'] = response

        # List all users
        response = self.superuser_client.list_user()
        assert_status(response, 200)
        responses['list_users'] = response

        # Retrieve a specific user
        response = self.superuser_client.get_user(self.customer_user.id)
        assert_status(response, 200)
        responses['get_user'] = response

        # List all images
        response = self.customer_client.list_image()
        assert_status(response, 200)
        responses['list_images'] = response

        response = self.superuser_client.list_image(
            data={'user_id': self.superuser.id}
        )
        assert_status(response, 200)
        responses['list_images_filter'] = response

        # Retrieve a specific image
        response = self.superuser_client.get_image(self.images[0].id)
        assert_status(response, 200)
        responses['get_image'] = response

        # Reinspect a specific image
        response = self.superuser_client.post_image(
            noun_id=self.images[0].id,
            detail='reinspect'
        )
        assert_status(response, 200)
        responses['reinspect_image'] = response

        # Issuing challenges/flags
        response = self.superuser_client.patch_image(
            self.images[0].id,
            data={'rhel_challenged': True, 'resourcetype': 'AwsMachineImage'},
        )
        assert_status(response, 200)
        responses['patch_image'] = response

        response = self.superuser_client.patch_image(
            self.images[0].id,
            data={'rhel_challenged': False, 'resourcetype': 'AwsMachineImage'},
        )
        assert_status(response, 200)
        responses['patch_image_false'] = response

        response = self.superuser_client.patch_image(
            self.images[0].id,
            data={
                'rhel_challenged': True,
                'openshift_challenged': True,
                'resourcetype': 'AwsMachineImage',
            },
        )
        assert_status(response, 200)
        responses['patch_image_both'] = response

        ########################
        # Miscellaneous Commands

        # Retrieve current cloud account ids used by the application
        cloudigrade_version = (
            '489-cloudigrade-version - '
            'd2b30c637ce3788e22990b21434bac2edcfb7ede'
        )
        with override_settings(CLOUDIGRADE_VERSION=cloudigrade_version):
            response = self.superuser_client.get_sysconfig()
        assert_status(response, 200)
        responses['get_sysconfig'] = response

        response = self.superuser_client.get_sysconfig()
        assert_status(response, 200)
        responses['get_sysconfig_no_version'] = response

        ########################
        # V2 endpoints
        responses['v2_rh_identity'] = util_helper.RH_IDENTITY
        # convert from binary string to string. 
        responses['v2_header'] = util_helper.get_3scale_auth_header().\
            decode("utf-8")

        with override_settings(CLOUDIGRADE_VERSION=cloudigrade_version):
            response = self.superuser_client.get_sysconfig(
                api_root='/api/v2'
            )
        assert_status(response, 200)
        responses['v2get_sysconfig'] = response

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
    loader = jinja2.FileSystemLoader(
        os.path.join(settings.ROOT_DIR, '..', 'docs')
    )
    env = jinja2.Environment(autoescape=False, loader=loader)

    env.filters['rst_codeblock'] = filters.rst_codeblock
    env.filters['stringify_http_response'] = filters.stringify_http_response
    env.filters['httpied_command'] = filters.httpied_command
    template = env.get_template('rest-api-examples.rst.jinja')
    return template.render(**data)


if __name__ == '__main__':
    empty_check()
    api_hander = DocsApiHandler()
    responses = api_hander.gather_api_responses()
    api_hander.cleanup()
    output = render(responses)
    output = '\n'.join((line.rstrip() for line in output.split('\n')))
    print(output)
