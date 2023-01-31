# Generated by Django 4.1.5 on 2023-01-30 18:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0068_alter_concurrentusage_potentially_related_runs_and_more"),
    ]

    # Update only Django's internal model representation to convert the old fields
    # without dropping and recreating table columns. We don't need to alter the database
    # schema because indexes and constraints were dropped in migration 0068.
    state_operations = [
        # SyntheticDataRequest.user to user_id
        migrations.AlterField(
            model_name="SyntheticDataRequest",
            name="user",
            field=models.IntegerField(db_index=False, null=True),
        ),
        migrations.RenameField(
            model_name="SyntheticDataRequest",
            old_name="user",
            new_name="user_id",
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[], state_operations=state_operations
        )
    ]