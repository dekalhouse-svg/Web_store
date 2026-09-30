from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0002_project_featured")]
    operations = [
        migrations.CreateModel(
            name="Visitor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("visitor_id", models.CharField(db_index=True, max_length=64, unique=True)),
                ("first_seen", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
