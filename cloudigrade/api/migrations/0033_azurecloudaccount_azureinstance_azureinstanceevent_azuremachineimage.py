# Generated by Django 3.0.9 on 2020-08-27 18:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0032_auto_20200826_1442"),
    ]

    operations = [
        migrations.CreateModel(
            name="AzureCloudAccount",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subscription_id", models.UUIDField()),
                ("tenant_id", models.UUIDField(unique=True)),
            ],
            options={"ordering": ("created_at",), "abstract": False,},
        ),
        migrations.CreateModel(
            name="AzureInstance",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "resource_id",
                    models.CharField(db_index=True, max_length=256, unique=True),
                ),
                ("region", models.CharField(max_length=256)),
            ],
            options={"ordering": ("created_at",), "abstract": False,},
        ),
        migrations.CreateModel(
            name="AzureInstanceEvent",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "instance_type",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
            ],
            options={"ordering": ("created_at",), "abstract": False,},
        ),
        migrations.CreateModel(
            name="AzureMachineImage",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "resource_id",
                    models.CharField(
                        blank=True, max_length=256, null=True, unique=True
                    ),
                ),
                ("azure_marketplace_image", models.BooleanField(default=False)),
                ("region", models.CharField(blank=True, max_length=256, null=True)),
            ],
            options={"ordering": ("created_at",), "abstract": False,},
        ),
    ]