# Generated by Django 2.0.6 on 2018-06-28 18:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0008_machineimage_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='AwsMachineImageCopy',
            fields=[
                ('awsmachineimage_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='account.AwsMachineImage')),
                ('reference_awsmachineimage', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='account.AwsMachineImage')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
            bases=('account.awsmachineimage',),
        ),
    ]
