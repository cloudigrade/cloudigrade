# Generated by Django 3.2.7 on 2021-09-30 16:11

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0048_awsmachineimage_product_codes"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="cloudaccount",
            unique_together={("platform_authentication_id", "platform_application_id")},
        ),
        migrations.RemoveField(
            model_name="cloudaccount",
            name="name",
        ),
    ]
