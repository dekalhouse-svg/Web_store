from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("store", "0013_sponsored_campaign_image")]

    operations = [
        migrations.AddField(
            model_name="visitor",
            name="token_hash",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddConstraint(
            model_name="visitor",
            constraint=models.UniqueConstraint(
                fields=("token_hash",), condition=~Q(token_hash=""),
                name="unique_nonempty_visitor_token_hash",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="visitor",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_events", to="store.visitor",
            ),
        ),
        migrations.AddIndex(
            model_name="event",
            index=models.Index(fields=["project", "visitor", "type", "created_at"], name="store_event_visit_dedupe_idx"),
        ),
        migrations.CreateModel(
            name="LoginAttemptByIP",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.CharField(db_index=True, max_length=254)),
                ("kind", models.CharField(choices=[("dev", "Développeur"), ("admin", "Administration")], max_length=10)),
                ("ip_hash", models.CharField(db_index=True, max_length=64)),
                ("failed_attempts", models.PositiveSmallIntegerField(default=0)),
                ("blocked_until", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("email", "kind", "ip_hash"), name="unique_login_attempt_ip_email_kind")],
            },
        ),
        migrations.CreateModel(
            name="RateLimitBucket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=64, unique=True)),
                ("window_started_at", models.DateTimeField(db_index=True)),
                ("count", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
