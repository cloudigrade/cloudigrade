# Generated by Django 2.1.10 on 2019-07-03 14:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0004_concurrentusage"),
    ]

    operations = [
        migrations.AddField(
            model_name="awscloudaccount",
            name="aws_access_key_id",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
    ]
