# Generated by Django 2.1 on 2018-08-22 15:01

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0020_make_is_encrypted_default_to_false'),
    ]

    operations = [
        migrations.AlterField(
            model_name='awsinstanceevent',
            name='instance_type',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AlterField(
            model_name='instanceevent',
            name='machineimage',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='account.MachineImage'),
        ),
    ]
