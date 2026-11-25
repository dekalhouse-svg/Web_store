import os

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction

from store.models import AdminRole


class Command(BaseCommand):
    help = "Garantit l'existence d'un unique fondateur sans modifier un fondateur déjà enregistré."

    @transaction.atomic
    def handle(self, *args, **options):
        founder_role = AdminRole.objects.select_for_update().select_related("user").filter(
            role=AdminRole.FOUNDER
        ).first()
        if founder_role:
            founder = founder_role.user
            changed = []
            if not founder.is_staff:
                founder.is_staff = True
                changed.append("is_staff")
            if not founder.is_superuser:
                founder.is_superuser = True
                changed.append("is_superuser")
            if changed:
                founder.save(update_fields=changed)
            for staff_user in User.objects.filter(is_staff=True).exclude(pk=founder.pk):
                if staff_user.is_superuser:
                    staff_user.is_superuser = False
                    staff_user.save(update_fields=["is_superuser"])
                AdminRole.objects.get_or_create(user=staff_user, defaults={"role": AdminRole.ADMIN})
            self.stdout.write(self.style.SUCCESS(
                f"Fondateur déjà enregistré : {founder.username}. Aucun mot de passe ni compte n'a été réinitialisé."
            ))
            return

        # Reprise automatique d'un superutilisateur déjà présent avant cette fonctionnalité.
        existing_superuser = User.objects.filter(is_superuser=True).order_by("date_joined", "id").first()
        if existing_superuser:
            role, _ = AdminRole.objects.update_or_create(
                user=existing_superuser,
                defaults={"role": AdminRole.FOUNDER, "created_by": None},
            )
            for staff_user in User.objects.filter(is_staff=True).exclude(pk=existing_superuser.pk):
                if staff_user.is_superuser:
                    staff_user.is_superuser = False
                    staff_user.save(update_fields=["is_superuser"])
                AdminRole.objects.get_or_create(user=staff_user, defaults={"role": AdminRole.ADMIN})
            self.stdout.write(self.style.SUCCESS(
                f"Fondateur enregistré à partir du compte existant : {role.user.username}."
            ))
            return

        email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        username = os.environ.get("ADMIN_USERNAME", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not email or not username or not password:
            raise CommandError(
                "Aucun fondateur n'existe. Configurez ADMIN_EMAIL, ADMIN_USERNAME et ADMIN_PASSWORD "
                "dans les variables Render pour initialiser le premier fondateur."
            )
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError("ADMIN_EMAIL n'est pas une adresse e-mail valide.")
        username_match = User.objects.filter(username__iexact=username).first()
        email_match = User.objects.filter(email__iexact=email).first()
        if username_match or email_match:
            if not username_match or not email_match or username_match.pk != email_match.pk:
                raise CommandError("ADMIN_USERNAME ou ADMIN_EMAIL appartient déjà à un autre compte.")
            user = username_match
            if not user.is_staff or not user.is_active:
                raise CommandError("Le compte correspondant n'est pas un compte administrateur actif ; aucun compte existant ne sera détourné.")
            user.is_superuser = True
            user.save(update_fields=["is_superuser"])
            AdminRole.objects.update_or_create(user=user, defaults={"role": AdminRole.FOUNDER, "created_by": None})
            for staff_user in User.objects.filter(is_staff=True).exclude(pk=user.pk):
                if staff_user.is_superuser:
                    staff_user.is_superuser = False
                    staff_user.save(update_fields=["is_superuser"])
                AdminRole.objects.get_or_create(user=staff_user, defaults={"role": AdminRole.ADMIN})
            self.stdout.write(self.style.SUCCESS(f"Compte administrateur existant promu fondateur : {user.username}."))
            return

        user = User(username=username, email=email, is_staff=True, is_superuser=True, is_active=True)
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError("Mot de passe fondateur invalide : " + " ".join(exc.messages))
        user.set_password(password)
        user.save()
        AdminRole.objects.create(user=user, role=AdminRole.FOUNDER)
        self.stdout.write(self.style.SUCCESS(f"Premier fondateur créé : {user.username}."))
