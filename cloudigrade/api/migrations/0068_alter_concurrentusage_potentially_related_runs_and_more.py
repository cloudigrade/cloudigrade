# Generated by Django 4.1.5 on 2023-01-30 18:39

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0067_remove_instance_cloud_account_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="concurrentusage",
            name="potentially_related_runs",
            field=models.ManyToManyField(db_constraint=False, to="api.run"),
        ),
        migrations.AlterField(
            model_name="syntheticdatarequest",
            name="machine_images",
            field=models.ManyToManyField(db_constraint=False, to="api.machineimage"),
        ),
        migrations.AlterField(
            model_name="syntheticdatarequest",
            name="user",
            field=models.OneToOneField(
                db_constraint=False,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="api.user",
            ),
        ),
    ]