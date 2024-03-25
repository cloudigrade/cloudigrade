"""Ensure Celery tasks are reasonable configured for cloudigrade."""

import os
import sys

import yaml
from celery import current_app as celery_app
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _


class Command(BaseCommand):
    """Ensure Celery tasks are reasonable configured for cloudigrade."""

    help = _("Ensures Celery tasks are reasonable configured for cloudigrade.")

    def get_clowdapp_yaml_celery_queue_names(self):
        """Get CELERY_QUEUE_NAMES from clowdapp.yml and as a set."""
        clowdapp_yaml_path = os.path.join(
            settings.ROOT_DIR, "..", "deployment", "clowdapp.yaml"
        )
        with open(clowdapp_yaml_path, "r") as clowdapp_yaml_file:
            clowdapp_yaml = yaml.safe_load(clowdapp_yaml_file)
        for yaml_object in clowdapp_yaml.get("parameters", []):
            if yaml_object.get("name") == "CELERY_QUEUE_NAMES":
                yaml_string = yaml_object.get("value", "")
                return set(yaml_string.replace(" ", "").split(","))
        return set()

    def handle(self, *args, **options):
        """Handle the command execution."""
        config_is_okay = True

        route_task_config = settings.CELERY_TASK_ROUTES

        # Check that all configured tasks have a queue defined.
        for task_name, config in route_task_config.items():
            if not config.get("queue"):
                self.stderr.write(
                    _(
                        "{task_name} is defined in CELERY_TASK_ROUTES "
                        "but does not configure a queue. "
                        "This may result in the task failing to execute!"
                    ).format(task_name=task_name),
                )
                config_is_okay = False

        route_task_names = set(route_task_config.keys())
        discovered_task_names = {
            task_name
            for task_name in celery_app.tasks.keys()
            if not task_name.startswith("celery.")  # ignore built-in celery tasks
        }
        enabled_scheduled_task_names = {
            info["task"]
            for key, info in celery_app.conf.beat_schedule.items()
            if info.get("enabled", True)
        }

        # Check that all defined routes have autodiscovered tasks.
        for missing_task in route_task_names - discovered_task_names:
            self.stderr.write(
                _(
                    "{missing_task} is defined in CELERY_TASK_ROUTES "
                    "but has not been autodiscovered. "
                    "This may result in the task failing to execute!"
                ).format(missing_task=missing_task),
            )
            config_is_okay = False

        # Check that all beat schedule items have autodiscovered tasks.
        for missing_task in enabled_scheduled_task_names - discovered_task_names:
            self.stderr.write(
                _(
                    "{missing_task} is enabled in beat_schedule "
                    "but has not been autodiscovered. "
                    "This may result in the task failing to execute!"
                ).format(missing_task=missing_task)
            )
            config_is_okay = False

        # Check that all beat schedule items have defined routes.
        for missing_task in enabled_scheduled_task_names - route_task_names:
            self.stderr.write(
                _(
                    "{missing_task} is enabled in beat_schedule "
                    "but is not defined in CELERY_TASK_ROUTES. "
                    "This may result in the task using the default celery queue!"
                ).format(missing_task=missing_task)
            )
            config_is_okay = False

        # check that all autodiscovered tasks have defined routes.
        for missing_task in discovered_task_names - route_task_names:
            self.stderr.write(
                _(
                    "{missing_task} is discovered "
                    "but is not defined in CELERY_TASK_ROUTES. "
                    "This may result in the task using the default celery queue!"
                ).format(missing_task=missing_task)
            )
            config_is_okay = False

        # Check that all configured task queues are in clowdapp.yaml.
        clowdapp_queue_names = self.get_clowdapp_yaml_celery_queue_names()
        configured_queue_names = {
            config.get("queue")
            for config in route_task_config.values()
            if config.get("queue")
        }
        for missing_queue in configured_queue_names - clowdapp_queue_names:
            self.stderr.write(
                _(
                    "{missing_queue} is defined in CELERY_TASK_ROUTES "
                    "but not in clowdapp.yml's CELERY_QUEUE_NAMES parameter. "
                    "This may result in the task never running!"
                ).format(missing_queue=missing_queue)
            )
            config_is_okay = False

        if not config_is_okay:
            sys.exit(1)
