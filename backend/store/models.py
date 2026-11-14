from django.db import models
from django.contrib.auth.models import User

class DeveloperProfile(models.Model):
    STATUS_CHOICES = [("ACTIF","ACTIF"),("SUSPENDU","SUSPENDU")]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="developer_profile")
    phone = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIF")
    email_verified = models.BooleanField(default=False)
    verification_code = models.CharField(max_length=20, blank=True)
    reset_code = models.CharField(max_length=20, blank=True)
    code_created_at = models.DateTimeField(null=True, blank=True)

class Visitor(models.Model):
    visitor_id = models.CharField(max_length=64, unique=True, db_index=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

class VisitorActivity(models.Model):
    TYPES = [("search", "search"), ("category", "category"), ("project_open", "project_open")]
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="activities")
    activity_type = models.CharField(max_length=20, choices=TYPES, db_index=True)
    search_query = models.CharField(max_length=300, blank=True)
    category = models.CharField(max_length=100, blank=True, db_index=True)
    project = models.ForeignKey("Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="visitor_activities")
    results_count = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["visitor", "activity_type", "created_at"])]

class CategoryRelation(models.Model):
    """Association administrable entre une catégorie et ses catégories voisines."""
    category = models.ForeignKey("Category", on_delete=models.CASCADE, related_name="neighbor_relations")
    neighbor = models.ForeignKey("Category", on_delete=models.CASCADE, related_name="related_from")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["category", "neighbor"], name="unique_category_neighbor")]

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    def __str__(self): return self.name

class Project(models.Model):
    TYPES = [("WEB","WEB"),("PWA","PWA")]
    STATUS = [("BROUILLON","BROUILLON"),("EN_ATTENTE","EN_ATTENTE"),("PUBLIE","PUBLIE"),("REJETE","REJETE"),("SUSPENDU","SUSPENDU")]
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=190, unique=True)
    description = models.TextField(blank=True)
    url = models.URLField(max_length=500)
    type = models.CharField(max_length=10, choices=TYPES, default="WEB")
    category = models.CharField(max_length=100, blank=True)
    tags = models.JSONField(default=list, blank=True)
    icon_data = models.TextField(blank=True)
    pwa_verified = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS, default="EN_ATTENTE")
    featured = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True)
    suspension_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Favorite(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="favorites")
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="favorites")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "visitor"], name="unique_project_visitor_favorite")]

class Comment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="comments")
    author_name = models.CharField(max_length=100)
    content = models.TextField(max_length=2000)
    # Jeton aléatoire dont seul le hash est conservé : autorise l'auteur anonyme
    # à gérer son commentaire sans créer de compte.
    manage_token_hash = models.CharField(max_length=64, blank=True, default="")
    visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, null=True, blank=True, related_name="comments")
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class CommentReport(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="reports")
    visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, null=True, blank=True, related_name="comment_reports")
    reason = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, default="OUVERT")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

class Report(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, default="OUVERT")
    created_at = models.DateTimeField(auto_now_add=True)

class Event(models.Model):
    TYPES = [("view","view"),("visit_click","visit_click"),("install","install")]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="events")
    type = models.CharField(max_length=30, choices=TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

class AuthToken(models.Model):
    key_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_tokens")
    kind = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_messages")
    subject = models.CharField(max_length=200)
    content = models.TextField(max_length=10000)
    read = models.BooleanField(default=False)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    created_at = models.DateTimeField(auto_now_add=True)

class ModerationLog(models.Model):
    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LoginAttempt(models.Model):
    """Limitation persistante des échecs de connexion par e-mail et espace."""
    email = models.CharField(max_length=254, db_index=True)
    kind = models.CharField(max_length=10, choices=[("dev", "Développeur"), ("admin", "Administration")])
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    blocked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["email", "kind"], name="unique_login_attempt_email_kind")]


class EmailCode(models.Model):
    """Code à usage unique : seul son HMAC est stocké en base."""
    PURPOSES = [
        ("verification", "Vérification d'e-mail"),
        ("password_reset", "Réinitialisation du mot de passe"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_codes")
    purpose = models.CharField(max_length=20, choices=PURPOSES)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "purpose"],
                name="unique_email_code_user_purpose",
            )
        ]


class SponsoredCampaign(models.Model):
    """Campagne de mise en avant d'un projet WEB STORE."""
    STATUS_CHOICES = [
        ("BROUILLON", "Brouillon"),
        ("EN_ATTENTE", "En attente de validation"),
        ("ACTIVE", "Active"),
        ("SUSPENDUE", "Suspendue"),
        ("REJETEE", "Rejetée"),
        ("TERMINEE", "Terminée"),
    ]
    PAYMENT_CHOICES = [
        ("NON_PAYE", "Paiement non confirmé"),
        ("A_VERIFIER", "Paiement à vérifier"),
        ("PAYE", "Paiement confirmé"),
        ("REFUSE", "Paiement refusé"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="sponsored_campaigns")
    title = models.CharField(max_length=160)
    target_categories = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="BROUILLON", db_index=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default="NON_PAYE", db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True, db_index=True)
    image_url = models.URLField(max_length=1000, blank=True)
    image_data = models.TextField(blank=True)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["ends_at", "-created_at"]
        indexes = [models.Index(fields=["status", "starts_at", "ends_at"], name="store_scamp_status_dates")]

    def __str__(self):
        return f"{self.title} — {self.project.name}"


class SponsoredCampaignEvent(models.Model):
    """Impression ou clic d'une campagne sponsorisée."""
    EVENT_TYPES = [("impression", "Impression"), ("click", "Clic")]
    campaign = models.ForeignKey(SponsoredCampaign, on_delete=models.CASCADE, related_name="events")
    visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, null=True, blank=True, related_name="sponsored_events")
    event_type = models.CharField(max_length=12, choices=EVENT_TYPES, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["campaign", "event_type", "created_at"], name="store_scamp_evt_stats_idx")]
