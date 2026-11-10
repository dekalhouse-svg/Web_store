from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def clear_test_comments(apps, schema_editor):
    apps.get_model("store", "Comment").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0007_email_code"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(clear_test_comments, migrations.RunPython.noop),
        migrations.CreateModel(
            name="Favorite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favorites", to="store.project")),
                ("visitor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favorites", to="store.visitor")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("project", "visitor"), name="unique_project_visitor_favorite")]},
        ),
    ]
