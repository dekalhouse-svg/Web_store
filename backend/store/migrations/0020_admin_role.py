from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_existing_founder(apps, schema_editor):
    AdminRole = apps.get_model("store", "AdminRole")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    # Le premier superutilisateur historique devient l'unique fondateur.
    founder = User.objects.filter(is_superuser=True).order_by("date_joined", "id").first()
    if founder:
        AdminRole.objects.get_or_create(user_id=founder.pk, defaults={"role": "FOUNDER"})
    # Les autres comptes staff/superuser sont des administrateurs ordinaires.
    for user in User.objects.filter(is_staff=True).exclude(pk=getattr(founder, "pk", None)).iterator():
        if user.is_superuser:
            user.is_superuser = False
            user.save(update_fields=["is_superuser"])
        AdminRole.objects.get_or_create(user_id=user.pk, defaults={"role": "ADMIN"})


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0019_pending_developer_registration"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AdminRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("FOUNDER", "Fondateur"), ("ADMIN", "Administrateur")], max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_admin_accounts", to=settings.AUTH_USER_MODEL)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="admin_role", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="adminrole",
            constraint=models.UniqueConstraint(condition=models.Q(("role", "FOUNDER")), fields=("role",), name="store_single_founder_role"),
        ),
        migrations.RunPython(assign_existing_founder, migrations.RunPython.noop),
    ]
