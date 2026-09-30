from django.core.management.base import BaseCommand
from store.models import Category
from django.utils.text import slugify

DEFAULTS=["Éducation","Business","Productivité","Technologie","Cybersécurité","Développement","Outils","Divertissement","Autre"]

class Command(BaseCommand):
    help="Ajoute les catégories de base si elles n'existent pas."
    def handle(self,*args,**kwargs):
        for name in DEFAULTS:
            Category.objects.get_or_create(slug=slugify(name),defaults={"name":name})
        self.stdout.write(self.style.SUCCESS("Catégories prêtes."))
