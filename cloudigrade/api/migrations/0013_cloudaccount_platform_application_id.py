# Generated by Django 3.0.4 on 2020-03-21 01:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0012_auto_20200219_2133"),
    ]

    operations = [
        migrations.AddField(
            model_name="cloudaccount",
            name="platform_application_id",
            field=models.IntegerField(null=True),
        ),
    ]
