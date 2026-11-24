# Generated for persistent notifications and Web Push subscriptions.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0016_admin_passkeys"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180)),
                ("body", models.TextField(blank=True, max_length=1000)),
                ("category", models.CharField(choices=[("message", "Message"), ("project", "Projet"), ("activity", "Activité"), ("system", "Système"), ("security", "Sécurité")], db_index=True, default="system", max_length=20)),
                ("target_url", models.CharField(blank=True, max_length=500)),
                ("is_read", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="webstore_notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["recipient", "is_read", "created_at"], name="store_notif_user_read_idx"),
        ),
        migrations.CreateModel(
            name="PushSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.URLField(max_length=2000, unique=True)),
                ("p256dh", models.CharField(max_length=255)),
                ("auth", models.CharField(max_length=255)),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="webpush_subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
    ]
