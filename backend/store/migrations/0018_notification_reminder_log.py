# Generated for scheduled developer notification reminders.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0017_notifications_push_subscriptions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationReminderLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reminder_key", models.CharField(db_index=True, max_length=255, unique=True)),
                ("reminder_type", models.CharField(max_length=30)),
                ("threshold_days", models.PositiveSmallIntegerField()),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notification_reminder_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-sent_at"]},
        ),
    ]
