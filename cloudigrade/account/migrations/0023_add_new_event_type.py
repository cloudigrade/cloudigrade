# Generated by Django 2.1 on 2018-10-04 16:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0022_awsec2instancedefinitions'),
    ]

    operations = [
        migrations.AlterField(
            model_name='instanceevent',
            name='event_type',
            field=models.CharField(choices=[('power_on', 'power_on'), ('power_off', 'power_off'), ('attribute_change', 'attribute_change')], max_length=32),
        ),
    ]
