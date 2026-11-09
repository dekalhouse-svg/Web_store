from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0006_comment_manage_token"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("purpose", models.CharField(choices=[("verification", "Vérification d'e-mail"), ("password_reset", "Réinitialisation du mot de passe")], max_length=20)),
                ("code_hash", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_sent_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="email_codes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("user", "purpose"), name="unique_email_code_user_purpose"),
                ],
            },
        ),
    ]
