# Generated by Django 3.2.7 on 2021-10-01 20:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0049_auto_20210930_1611"),
    ]

    operations = [
        migrations.AddField(
            model_name="awsmachineimage",
            name="platform_details",
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
    ]
