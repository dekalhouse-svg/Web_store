# Create pending registrations so unverified developers are not User records.
from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0018_notification_reminder_log"),
    ]

    operations = [
        migrations.CreateModel(
            name="PendingDeveloperRegistration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=150)),
                ("username", models.CharField(max_length=150, unique=True)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("password_hash", models.CharField(max_length=256)),
                ("code_hash", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_sent_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"indexes": [models.Index(fields=["expires_at"], name="store_pend_expire_idx")]},
        ),
        migrations.AddConstraint(
            model_name="pendingdeveloperregistration",
            constraint=models.UniqueConstraint(Lower("username"), name="uniq_pending_dev_username_ci"),
        ),
        migrations.AddConstraint(
            model_name="pendingdeveloperregistration",
            constraint=models.UniqueConstraint(Lower("email"), name="uniq_pending_dev_email_ci"),
        ),
    ]
