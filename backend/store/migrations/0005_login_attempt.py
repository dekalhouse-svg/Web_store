from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("store", "0004_project_icon_pwa")]
    operations = [
        migrations.CreateModel(
            name="LoginAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.CharField(db_index=True, max_length=254)),
                ("kind", models.CharField(choices=[("dev", "Développeur"), ("admin", "Administration")], max_length=10)),
                ("failed_attempts", models.PositiveSmallIntegerField(default=0)),
                ("blocked_until", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("email", "kind"), name="unique_login_attempt_email_kind")
                ]
            },
        ),
    ]
