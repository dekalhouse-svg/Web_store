from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("store", "0009_comment_visitor_reports")]

    operations = [
        migrations.CreateModel(
            name="VisitorActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("activity_type", models.CharField(choices=[("search", "search"), ("category", "category"), ("project_open", "project_open")], db_index=True, max_length=20)),
                ("search_query", models.CharField(blank=True, max_length=300)),
                ("category", models.CharField(blank=True, db_index=True, max_length=100)),
                ("results_count", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="visitor_activities", to="store.project")),
                ("visitor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activities", to="store.visitor")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="visitoractivity",
            index=models.Index(fields=["visitor", "activity_type", "created_at"], name="store_visact_vt_type_dt_idx"),
        ),
    ]
