# Generated by Django 4.1.5 on 2023-01-25 16:50

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0065_delete_periodic_metering_tasks"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="concurrentusage",
            options={"ordering": ("created_at",)},
        ),
        migrations.AlterUniqueTogether(
            name="concurrentusage",
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name="awsmachineimagecopy",
            name="reference_awsmachineimage",
            field=models.ForeignKey(
                db_constraint=False,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="api.awsmachineimage",
            ),
        ),
        migrations.AlterField(
            model_name="concurrentusage",
            name="user",
            field=models.ForeignKey(
                db_constraint=False,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="api.user",
            ),
        ),
        migrations.AlterField(
            model_name="instance",
            name="cloud_account",
            field=models.ForeignKey(
                db_constraint=False,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="api.cloudaccount",
            ),
        ),
        migrations.AlterField(
            model_name="instance",
            name="machine_image",
            field=models.ForeignKey(
                db_constraint=False,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="api.machineimage",
            ),
        ),
        migrations.AlterField(
            model_name="instanceevent",
            name="instance",
            field=models.ForeignKey(
                db_constraint=False,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="api.instance",
            ),
        ),
        migrations.AlterField(
            model_name="machineimageinspectionstart",
            name="machineimage",
            field=models.ForeignKey(
                db_constraint=False,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="api.machineimage",
            ),
        ),
        migrations.AlterField(
            model_name="run",
            name="instance",
            field=models.ForeignKey(
                db_constraint=False,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="api.instance",
            ),
        ),
        migrations.AlterField(
            model_name="run",
            name="machineimage",
            field=models.ForeignKey(
                db_constraint=False,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="api.machineimage",
            ),
        ),
    ]
