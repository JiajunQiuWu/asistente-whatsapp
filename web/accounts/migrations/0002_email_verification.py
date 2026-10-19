from collections import defaultdict

from django.db import migrations, models
from django.db.models import Q
from django.db.models.functions import Lower


def check_duplicate_emails(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    duplicates = defaultdict(list)
    for user_id, username, email in User.objects.using(schema_editor.connection.alias).exclude(
        email=""
    ).values_list("id", "username", "email"):
        duplicates[email.casefold()].append((user_id, username, email))

    conflicts = [
        entries
        for entries in duplicates.values()
        if len(entries) > 1
    ]
    if conflicts:
        details = "; ".join(
            f"{entries[0][2]!r}: "
            + ", ".join(
                f"id={user_id} username={username!r}"
                for user_id, username, _email in entries
            )
            for entries in conflicts
        )
        raise RuntimeError(
            "No se puede aplicar la migración: hay direcciones de correo "
            "duplicadas sin distinguir mayúsculas/minúsculas. Resuelve "
            "manualmente estas cuentas (no se han modificado): "
            f"{details}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            check_duplicate_emails,
            migrations.RunPython.noop,
        ),
        migrations.AddField(
            model_name="user",
            name="email_verified_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="correo verificado el",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="verification_email_sent_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="último correo de verificación enviado",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="accounts_user_email_ci_unique",
            ),
        ),
    ]
