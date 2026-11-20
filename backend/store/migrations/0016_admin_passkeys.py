from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("store", "0015_developerprofile_avatar_data"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="AdminPasskey", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("credential_id", models.CharField(max_length=2048, unique=True)),
            ("public_key", models.TextField()), ("sign_count", models.PositiveBigIntegerField(default=0)),
            ("device_name", models.CharField(blank=True, default="", max_length=100)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("last_used_at", models.DateTimeField(blank=True, null=True)),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="admin_passkeys", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at"]}),
        migrations.CreateModel(name="AdminAuthChallenge", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("purpose", models.CharField(choices=[("register", "Enregistrement"), ("login", "Connexion")], max_length=12)),
            ("challenge", models.CharField(blank=True, default="", max_length=256)),
            ("token_hash", models.CharField(blank=True, db_index=True, default="", max_length=64)),
            ("email_code_hash", models.CharField(blank=True, default="", max_length=64)),
            ("email_sent_at", models.DateTimeField(blank=True, null=True)),
            ("attempts", models.PositiveSmallIntegerField(default=0)), ("expires_at", models.DateTimeField(db_index=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="admin_auth_challenges", to=settings.AUTH_USER_MODEL)),
        ]),
    ]
