# Generated by Django 2.2.3 on 2019-07-24 20:55

from django.db import migrations, models


def delete_concurrentusage(apps, schema_editor):
    """Delete all concurrentusage objects (again)."""
    ConcurrentUsage = apps.get_model("api", "ConcurrentUsage")
    ConcurrentUsage.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0008_delete_concurrentusage"),
    ]

    operations = [
        migrations.RunPython(delete_concurrentusage),
        migrations.AddField(
            model_name="concurrentusage",
            name="potentially_related_runs",
            field=models.ManyToManyField(to="api.Run"),
        ),
    ]
