# Generated by Django 3.0.6 on 2020-05-26 19:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0022_reset_verify_task_schedules"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineimage",
            name="architecture",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
    ]