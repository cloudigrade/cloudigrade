# Generated by Django 3.0.4 on 2020-04-13 19:08

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("api", "0018_cloudaccount_platform_not_null"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="cloudaccount",
            unique_together={
                ("platform_authentication_id", "platform_application_id"),
                ("user", "name"),
            },
        ),
    ]
