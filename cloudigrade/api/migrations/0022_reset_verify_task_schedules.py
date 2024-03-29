# Generated by Django 3.0.6 on 2020-05-26 17:56
from django.db import migrations


def reset_verify_tasks(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=60 * 60 * 24,  # 24 hours
        period="seconds",
    )

    for task in PeriodicTask.objects.filter(
        task="api.clouds.aws.tasks.verify_account_permissions"
    ):
        task.interval = schedule
        task.save()


class Migration(migrations.Migration):

    dependencies = [
        ("django_celery_beat", "0011_auto_20190508_0153"),
        ("api", "0021_delete_orphaned_periodic_tasks"),
    ]

    operations = [
        migrations.RunPython(reset_verify_tasks),
    ]
