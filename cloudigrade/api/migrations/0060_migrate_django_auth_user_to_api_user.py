import uuid
from django.db import migrations
from django.contrib.auth.models import User as DjangoUser

from api.models import User as ApiUser


def migrate_django_auth_user_to_api_user(_apps, _schema_editor):
    """Migrate Django auth users to api users."""

    for user in DjangoUser.objects.all():
        if ApiUser.objects.filter(id=user.id).exists():
            ApiUser.objects.filter(id=user.id).update(
                uuid=str(uuid.uuid4()),
                password=user.password,
                account_number=user.username,
                is_active=user.is_active,
                is_superuser=user.is_superuser,
                date_joined=user.date_joined,
            )
        else:
            ApiUser.objects.create(
                id=user.id,
                uuid=str(uuid.uuid4()),
                password=user.password,
                account_number=user.username,
                is_active=user.is_active,
                is_superuser=user.is_superuser,
                date_joined=user.date_joined,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0059_api_user"),
    ]

    operations = [
        # Adding the noop backward migration to allow for debugging.
        migrations.RunPython(
            migrate_django_auth_user_to_api_user, migrations.RunPython.noop
        )
    ]
