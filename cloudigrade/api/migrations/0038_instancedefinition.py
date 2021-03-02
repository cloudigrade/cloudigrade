# Generated by Django 3.1.7 on 2021-03-02 15:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0037_delete_instance_definition"),
    ]

    operations = [
        migrations.CreateModel(
            name="InstanceDefinition",
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
                ("instance_type", models.CharField(db_index=True, max_length=256)),
                ("memory", models.IntegerField(default=0)),
                ("vcpu", models.IntegerField(default=0)),
                ("json_definition", models.JSONField()),
                (
                    "cloud_type",
                    models.CharField(
                        choices=[
                            ("aws", "AWS EC2 instance definitions."),
                            ("azure", "Azure VM instance definitions."),
                        ],
                        max_length=32,
                    ),
                ),
            ],
            options={
                "unique_together": {("instance_type", "cloud_type")},
            },
        ),
    ]
