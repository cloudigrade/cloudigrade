# Generated by Django 3.2.5 on 2021-07-19 21:15

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0041_auto_20210701_2050"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ConcurrentUsageCalculationTask",
        ),
    ]
