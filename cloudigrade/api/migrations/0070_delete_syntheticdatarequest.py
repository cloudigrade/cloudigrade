# Generated by Django 4.1.5 on 2023-01-30 19:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0069_remove_syntheticdatarequest_user_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="SyntheticDataRequest",
        ),
    ]