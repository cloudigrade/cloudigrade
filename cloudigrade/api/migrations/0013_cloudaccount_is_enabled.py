# Generated by Django 3.0.3 on 2020-03-09 18:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0012_auto_20200219_2133"),
    ]

    operations = [
        migrations.AddField(
            model_name="cloudaccount",
            name="is_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
