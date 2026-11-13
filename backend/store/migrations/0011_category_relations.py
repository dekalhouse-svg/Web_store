from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("store", "0010_visitor_activity")]
    operations = [
        migrations.CreateModel(
            name="CategoryRelation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="neighbor_relations", to="store.category")),
                ("neighbor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="related_from", to="store.category")),
            ],
        ),
        migrations.AddConstraint(model_name="categoryrelation", constraint=models.UniqueConstraint(fields=("category", "neighbor"), name="unique_category_neighbor")),
    ]
