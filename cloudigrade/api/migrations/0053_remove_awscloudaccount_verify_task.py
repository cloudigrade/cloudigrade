# Generated by Django 3.2.10 on 2021-12-20 18:57

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0052_auto_20211215_2157"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="awscloudaccount",
            name="verify_task",
        ),
    ]
