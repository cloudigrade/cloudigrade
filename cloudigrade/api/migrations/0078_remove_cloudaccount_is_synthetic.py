# Generated by Django 4.1.6 on 2023-02-02 18:50

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0077_delete_periodic_tasks"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="cloudaccount",
            name="is_synthetic",
        ),
    ]
