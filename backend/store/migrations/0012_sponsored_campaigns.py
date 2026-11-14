from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("store", "0011_category_relations")]

    operations = [
        migrations.CreateModel(
            name="SponsoredCampaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=160)),
                ("target_categories", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("BROUILLON", "Brouillon"), ("EN_ATTENTE", "En attente de validation"), ("ACTIVE", "Active"), ("SUSPENDUE", "Suspendue"), ("REJETEE", "Rejetée"), ("TERMINEE", "Terminée")], db_index=True, default="BROUILLON", max_length=20)),
                ("payment_status", models.CharField(choices=[("NON_PAYE", "Paiement non confirmé"), ("A_VERIFIER", "Paiement à vérifier"), ("PAYE", "Paiement confirmé"), ("REFUSE", "Paiement refusé")], db_index=True, default="NON_PAYE", max_length=20)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("image_url", models.URLField(blank=True, max_length=1000)),
                ("admin_note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sponsored_campaigns", to="store.project")),
            ],
            options={"ordering": ["ends_at", "-created_at"]},
        ),
        migrations.AddIndex(model_name="sponsoredcampaign", index=models.Index(fields=["status", "starts_at", "ends_at"], name="store_scamp_status_dates")),
        migrations.CreateModel(
            name="SponsoredCampaignEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("impression", "Impression"), ("click", "Clic")], db_index=True, max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="store.sponsoredcampaign")),
                ("visitor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sponsored_events", to="store.visitor")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="sponsoredcampaignevent", index=models.Index(fields=["campaign", "event_type", "created_at"], name="store_scamp_evt_stats_idx")),
    ]
