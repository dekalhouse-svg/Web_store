from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency("auth.User"),
    ]
    operations = [
        migrations.CreateModel(
            name="AuthToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key_hash", models.CharField(max_length=64, unique=True)),
                ("kind", models.CharField(max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_tokens", to="auth.user")),
            ],
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("slug", models.SlugField(max_length=120, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name="DeveloperProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("status", models.CharField(choices=[("ACTIF","ACTIF"),("SUSPENDU","SUSPENDU")], default="ACTIF", max_length=20)),
                ("email_verified", models.BooleanField(default=False)),
                ("verification_code", models.CharField(blank=True, max_length=20)),
                ("reset_code", models.CharField(blank=True, max_length=20)),
                ("code_created_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="developer_profile", to="auth.user")),
            ],
        ),
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("slug", models.SlugField(max_length=190, unique=True)),
                ("description", models.TextField(blank=True)),
                ("url", models.URLField(max_length=500)),
                ("type", models.CharField(choices=[("WEB","WEB"),("PWA","PWA")], default="WEB", max_length=10)),
                ("category", models.CharField(blank=True, max_length=100)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("BROUILLON","BROUILLON"),("EN_ATTENTE","EN_ATTENTE"),("PUBLIE","PUBLIE"),("REJETE","REJETE"),("SUSPENDU","SUSPENDU")], default="EN_ATTENTE", max_length=20)),
                ("rejection_reason", models.TextField(blank=True)),
                ("suspension_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("developer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="projects", to="auth.user")),
            ],
        ),
        migrations.CreateModel(
            name="Comment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("author_name", models.CharField(max_length=100)),
                ("content", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="store.project")),
            ],
        ),
        migrations.CreateModel(
            name="Event",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type", models.CharField(choices=[("view","view"),("visit_click","visit_click"),("install","install")], max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="store.project")),
            ],
        ),
        migrations.CreateModel(
            name="Report",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("status", models.CharField(default="OUVERT", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reports", to="store.project")),
            ],
        ),
        migrations.CreateModel(
            name="Message",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject", models.CharField(max_length=200)),
                ("content", models.TextField(max_length=10000)),
                ("read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="replies", to="store.message")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="received_messages", to="auth.user")),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sent_messages", to="auth.user")),
            ],
        ),
        migrations.CreateModel(
            name="ModerationLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=50)),
                ("reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("admin", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="auth.user")),
                ("project", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="store.project")),
            ],
        ),
    ]
