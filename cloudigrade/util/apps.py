from django.apps import AppConfig


class UtilConfig(AppConfig):
    name = "util"

    # TODO FIXME: Health checks previously present here
    # were causing a memory leak issue, when the time comes we need
    # to come back and refactor or replace these health checks.
