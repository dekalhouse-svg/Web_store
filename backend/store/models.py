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
    status = models.CharField(max_length=20, choices=STATUS, default="EN_ATTENTE")
    featured = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True)
    suspension_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Comment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="comments")
    author_name = models.CharField(max_length=100)
    content = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

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
