import hashlib, secrets, base64, re, json, hmac, uuid
from html import escape as html_escape
from datetime import timedelta
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse, urlsplit, quote
import socket, ipaddress, ssl, http.client
from urllib.request import Request, urlopen
from functools import wraps
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import make_password, check_password
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.text import slugify
from .models import DeveloperProfile, Category, Project, Comment, Report, Event, AuthToken, Message, ModerationLog, Visitor, EmailCode, PendingDeveloperRegistration, Favorite, CommentReport, VisitorActivity, CategoryRelation, SponsoredCampaign, SponsoredCampaignEvent, LoginAttemptByIP, RateLimitBucket, AdminPasskey, AdminAuthChallenge, Notification, PushSubscription, AdminRole
from .telegram_security import notify_admin_login

def json_body(request):
    import json
    try: return json.loads(request.body or b"{}")
    except Exception: return {}

def ok(data=None, status=200):
    return JsonResponse(data if data is not None else {}, status=status, safe=not isinstance(data, list))

def err(message, status=400):
    return JsonResponse({"detail": message}, status=status)

def health(request): return ok({"service":"WEB STORE API","status":"ok"})
def api_root(request): return ok({"service":"WEB STORE API","version":"1.0"})

def hash_token(raw): return hashlib.sha256(raw.encode()).hexdigest()

def valid_project_url(value):
    try:
        parsed = urlparse(str(value).strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False
def issue_token(user, kind, request=None):
    raw = secrets.token_urlsafe(32)
    AuthToken.objects.create(key_hash=hash_token(raw), user=user, kind=kind)
    return raw

API_TOKEN_TTL = timedelta(days=30)
ADMIN_API_TOKEN_TTL = timedelta(hours=12)


def _client_ip(request):
    # REMOTE_ADDR évite de faire confiance à un X-Forwarded-For fourni par le client.
    return (request.META.get("REMOTE_ADDR") or "unknown")[:64]


def _rate_limited(request, scope, limit, window_seconds, identity=""):
    """Limitation atomique en base, partagée entre les workers et fail-closed."""
    material = f"{scope}:{_client_ip(request)}:{identity}"
    key = hashlib.sha256(material.encode("utf-8")).hexdigest()
    now = timezone.now()
    try:
        with transaction.atomic():
            bucket, created = RateLimitBucket.objects.get_or_create(
                key=key,
                defaults={"window_started_at": now, "count": 1},
            )
            bucket = RateLimitBucket.objects.select_for_update().get(pk=bucket.pk)
            if not created:
                if bucket.window_started_at <= now - timedelta(seconds=window_seconds):
                    bucket.window_started_at = now
                    bucket.count = 1
                else:
                    bucket.count += 1
                bucket.save(update_fields=["window_started_at", "count", "updated_at"])
            count = bucket.count
        # Nettoyage opportuniste des clés expirées pour éviter une croissance infinie.
        if secrets.randbelow(500) == 0:
            RateLimitBucket.objects.filter(window_started_at__lt=now - timedelta(days=2)).delete()
        return count > limit
    except Exception:
        # En cas d'indisponibilité du stockage de limitation, on refuse l'action sensible.
        return True


def _visitor_from_request(request):
    """Retourne un visiteur uniquement si le secret anonyme est valide."""
    raw = request.headers.get("X-Visitor-Token", "").strip()
    if not raw or len(raw) > 128 or not re.fullmatch(r"[A-Za-z0-9_-]{40,128}", raw):
        return None
    return Visitor.objects.filter(token_hash=hash_token(raw)).first()


def _visitor_rate_identity(request):
    """Sépare les compteurs des visiteurs tout en conservant la limite par IP."""
    raw = request.headers.get("X-Visitor-Token", "").strip()
    return hash_token(raw) if raw and len(raw) <= 128 else "anonymous"


def auth_user(request, kind=None):
    value=request.headers.get("Authorization","")
    if not value.startswith("Bearer "): return None
    raw=value[7:].strip()
    if not raw: return None
    token=AuthToken.objects.select_related("user").filter(key_hash=hash_token(raw)).first()
    if not token: return None
    if kind and token.kind != kind: return None
    if not token.user.is_active: return None
    token_ttl = ADMIN_API_TOKEN_TTL if token.kind == "admin" else API_TOKEN_TTL
    if token.created_at <= timezone.now() - token_ttl:
        token.delete()
        return None
    token.last_used_at=timezone.now(); token.save(update_fields=["last_used_at"])
    return token.user

def require(kind):
    def deco(fn):
        @wraps(fn)
        def wrapped(request,*args,**kwargs):
            user=auth_user(request,kind)
            if not user: return err("Authentification requise.",401)
            request.api_user=user
            return fn(request,*args,**kwargs)
        return wrapped
    return deco


def admin_only(fn):
    return require("admin")(fn)

def founder_only(fn):
    """Réserve les opérations de gouvernance au fondateur enregistré en base."""
    @wraps(fn)
    def wrapped(request, *args, **kwargs):
        user = auth_user(request, "admin")
        if not user:
            return err("Authentification requise.", 401)
        request.api_user = user
        if not AdminRole.objects.filter(user=user, role=AdminRole.FOUNDER).exists():
            return err("Cette opération est réservée au fondateur.", 403)
        return fn(request, *args, **kwargs)
    return wrapped

def _admin_role_name(user):
    role = AdminRole.objects.filter(user=user).values_list("role", flat=True).first()
    return role or (AdminRole.ADMIN if user.is_staff else "")

def _safe_public_fetch(url, max_bytes, redirects=3):
    """Télécharge une ressource HTTP(S) publique sans suivre de redirection non vérifiée.

    La connexion est établie directement vers une IP publique préalablement résolue,
    afin d'éviter les accès aux réseaux privés/locaux et le DNS rebinding classique.
    """
    current_url = url

    for _ in range(redirects + 1):
        parsed = urlsplit(current_url)
        if parsed.scheme not in {"http", "https"}:
            return None
        if not parsed.hostname or parsed.username or parsed.password:
            return None

        host = parsed.hostname.rstrip(".")
        if host.lower() == "localhost" or host.lower().endswith((".localhost", ".local", ".internal")):
            return None

        default_port = 443 if parsed.scheme == "https" else 80
        try:
            port = parsed.port or default_port
        except ValueError:
            return None
        if port != default_port:
            return None

        sock = None
        try:
            addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            public_ips = []
            for item in addresses:
                ip = ipaddress.ip_address(item[4][0].split("%")[0])
                if not ip.is_global:
                    return None
                public_ips.append(str(ip))
            if not public_ips:
                return None

            # Connexion directe à l'IP contrôlée : le nom d'hôte reste utilisé
            # pour l'en-tête Host et, en HTTPS, pour la vérification TLS/SNI.
            sock = socket.create_connection((public_ips[0], port), timeout=5)
            if parsed.scheme == "https":
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)

            path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
            if parsed.query:
                path += "?" + quote(parsed.query, safe="=&?/:@!$'()*+,;%-._~")
            display_host = f"[{host}]" if ":" in host else host
            host_header = display_host if port == default_port else f"{display_host}:{port}"
            request_data = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                "User-Agent: WEB-STORE-PWA-Checker/1.0\r\n"
                "Accept: text/html,application/json\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            sock.sendall(request_data)

            response = http.client.HTTPResponse(sock)
            response.begin()
            status = response.status
            location = response.getheader("Location")
            content_type = response.getheader("Content-Type", "")
            if status in {301, 302, 303, 307, 308} and location:
                response.close()
                sock.close()
                current_url = urljoin(current_url, location)
                continue
            if status != 200:
                response.close()
                sock.close()
                return None

            body = response.read(max_bytes + 1)
            response.close()
            sock.close()
            if len(body) > max_bytes:
                return None
            return content_type, body
        except Exception:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
            return None

    return None


def verify_pwa_url(url):
    """Vérifie les éléments essentiels d'une PWA en n'accédant qu'à des hôtes publics."""
    try:
        page = _safe_public_fetch(url, 300000)
        if not page:
            return False
        content_type, html_bytes = page
        if "text/html" not in content_type and not content_type.startswith("text/"):
            return False
        html = html_bytes.decode("utf-8", errors="ignore")

        manifest_match = re.search(
            r'<link[^>]+rel=["\\\'](?:manifest|manifest\\s+[^"\\\']*)["\\\'][^>]+href=["\\\']([^"\\\']+)',
            html, re.IGNORECASE
        )
        if not manifest_match:
            manifest_match = re.search(
                r'<link[^>]+href=["\\\']([^"\\\']+)["\\\'][^>]+rel=["\\\'](?:manifest|manifest\\s+[^"\\\']*)["\\\']',
                html, re.IGNORECASE
            )
        if not manifest_match:
            return False

        manifest_url = urljoin(url, manifest_match.group(1))
        manifest_response = _safe_public_fetch(manifest_url, 200000)
        if not manifest_response:
            return False
        _, manifest_bytes = manifest_response
        manifest = json.loads(manifest_bytes.decode("utf-8", errors="ignore"))

        has_manifest_basics = bool(manifest.get("name") or manifest.get("short_name")) and bool(manifest.get("start_url"))
        has_service_worker_registration = bool(
            re.search(r'navigator\.serviceWorker\.register\s*\(', html, re.IGNORECASE)
        )
        return has_manifest_basics and has_service_worker_registration
    except Exception:
        return False

def project_public(p):
    return {"id":p.id,"name":p.name,"slug":p.slug,"description":p.description,"url":p.url,
            "type":p.type,"category":p.category,"category_slug":slugify(p.category) if p.category else "all","tags":p.tags,"status":p.status,"featured":p.featured,
            "icon_data":p.icon_data,"pwa_verified":p.pwa_verified,
            "developer_id":p.developer_id,"developer_name":p.developer.get_full_name() or p.developer.username,
            "favorites_count":p.favorites.count(),
            "created_at":p.created_at.isoformat()}

def project_detail_public(p):
    d = project_public(p)
    d["comments"] = [{"id": c.id, "author_name": c.author_name, "content": c.content, "created_at": c.created_at.isoformat()} for c in p.comments.filter(is_hidden=False).order_by("-created_at")]
    event_counts = p.events.values("type").annotate(total=Count("id"))
    counts = {item["type"]: item["total"] for item in event_counts}
    d["visits_count"] = counts.get("visit_click", 0)
    d["views_count"] = counts.get("view", 0)
    d["installs_count"] = counts.get("install", 0)
    return d

@csrf_exempt
def visitor_track(request):
    if request.method != "POST": return err("Méthode non autorisée.",405)
    if _rate_limited(request, "visitor_track", 300, 600, identity=hash_token(request.META.get("HTTP_USER_AGENT", "")[:200])):
        return err("Trop de demandes d'identification. Réessayez plus tard.", 429)

    raw_token = request.headers.get("X-Visitor-Token", "").strip()
    visitor = None
    if raw_token and len(raw_token) <= 128 and re.fullmatch(r"[A-Za-z0-9_-]{40,128}", raw_token):
        visitor = Visitor.objects.filter(token_hash=hash_token(raw_token)).first()

    if visitor:
        visitor.save(update_fields=["last_seen"])
        return ok({"visitor_id": visitor.visitor_id, "new_visitor": False})

    # L'ancien X-Visitor-ID n'est volontairement jamais utilisé pour récupérer
    # un visiteur existant : il n'était pas un secret et pouvait être usurpé.
    raw_token = secrets.token_urlsafe(32)
    visitor_id = secrets.token_urlsafe(24)
    visitor = Visitor.objects.create(visitor_id=visitor_id, token_hash=hash_token(raw_token))
    return ok({"visitor_id": visitor.visitor_id, "visitor_token": raw_token, "new_visitor": True}, 201)

@csrf_exempt
def visitor_activity(request):
    if request.method != "POST": return err("Méthode non autorisée.", 405)
    if _rate_limited(request, "visitor_activity_ip", 600, 60):
        return err("Trop d'activités depuis cette connexion. Réessayez plus tard.", 429)
    if _rate_limited(request, "visitor_activity", 60, 60, identity=_visitor_rate_identity(request)):
        return err("Trop d'activités. Réessayez plus tard.", 429)
    visitor = _visitor_from_request(request)
    if not visitor: return err("Identité visiteur invalide. Rechargez la page.", 401)
    body = json_body(request)
    activity_type = str(body.get("type", "")).strip()
    if activity_type not in {"search", "category", "project_open"}:
        return err("Type d'activité invalide.")
    search_query = str(body.get("query", "")).strip()[:300]
    category = str(body.get("category", "")).strip()[:100]
    project = None
    results_count = body.get("results_count")
    if activity_type == "search" and not search_query:
        return err("Recherche vide ignorée.")
    if activity_type == "category" and not category:
        return err("Catégorie manquante.")
    if activity_type == "project_open":
        slug = str(body.get("project_slug", "")).strip()
        project = Project.objects.filter(slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]).first()
        if not project: return err("Projet introuvable.", 404)
        category = project.category or "Autre"
    if results_count is not None:
        try: results_count = max(0, min(int(results_count), 1000000))
        except (TypeError, ValueError): results_count = None
    activity = VisitorActivity.objects.create(
        visitor=visitor, activity_type=activity_type, search_query=search_query,
        category=category, project=project, results_count=results_count,
    )
    return ok({"id": activity.id, "message": "Activité enregistrée."}, 201)

@csrf_exempt
def categories(request):
    if request.method!="GET": return err("Méthode non autorisée.",405)
    cats=list(Category.objects.order_by("name").values("id","name","slug"))
    return ok(cats)

def project_list_public(p):
    """Payload léger pour la liste publique : les octets d'icône sont servis séparément."""
    return {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "short_description": (p.description or "")[:180],
        "url": p.url,
        "type": p.type,
        "category": p.category,
        "category_slug": slugify(p.category) if p.category else "all",
        "tags": p.tags,
        "status": p.status,
        "featured": p.featured,
        "icon_url": f"/projects/{p.slug}/icon/" if p.icon_data else "",
        "pwa_verified": p.pwa_verified,
        "developer_id": p.developer_id,
        "developer_name": p.developer.get_full_name() or p.developer.username,
        "favorites_count": p.favorites.count(),
        "created_at": p.created_at.isoformat(),
    }

@csrf_exempt
def public_projects(request):
    if request.method!="GET": return err("Méthode non autorisée.",405)
    # Ne charge pas les données Base64 des icônes dans la réponse du catalogue.
    qs=Project.objects.filter(status__in=["EN_ATTENTE", "PUBLIE"]).select_related("developer").defer("icon_data")
    search=request.GET.get("search","").strip()
    category=request.GET.get("category","").strip()
    if search: qs=qs.filter(Q(name__icontains=search)|Q(description__icontains=search)|Q(tags__icontains=search))
    if category: qs=qs.filter(category__iexact=category)
    try:
        page = max(1, int(request.GET.get("page", "1")))
        page_size = min(100, max(1, int(request.GET.get("page_size", "100"))))
    except (TypeError, ValueError):
        return err("Paramètres de pagination invalides.", 400)
    start = (page - 1) * page_size
    items = qs.order_by("-featured", "-created_at")[start:start + page_size]
    return ok([project_list_public(p) for p in items])

@csrf_exempt
def public_project_icon(request, slug):
    """Renvoie une seule icône, sans l'embarquer dans le JSON du catalogue."""
    if request.method != "GET": return err("Méthode non autorisée.", 405)
    p = Project.objects.only("icon_data", "status").filter(
        slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]
    ).first()
    if not p or not p.icon_data:
        return err("Icône introuvable.", 404)
    try:
        header, separator, encoded = p.icon_data.partition(",")
        if not separator or not header.startswith("data:image/"):
            return err("Icône invalide.", 404)
        mime = header[5:].split(";")[0].lower()
        if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            return err("Format d'icône non pris en charge.", 404)
        raw = base64.b64decode(encoded, validate=True)
    except Exception:
        return err("Icône invalide.", 404)
    response = HttpResponse(raw, content_type=mime)
    response["Cache-Control"] = "public, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    return response

@csrf_exempt
def public_project(request,slug):
    if request.method!="GET": return err("Méthode non autorisée.",405)
    p=Project.objects.select_related("developer").filter(slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]).first()
    if not p: return err("Projet introuvable.",404)
    return ok(project_detail_public(p))

@csrf_exempt
def public_similar_projects(request, slug):
    if request.method != "GET": return err("Méthode non autorisée.", 405)
    project = Project.objects.filter(slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]).first()
    if not project: return err("Projet introuvable.", 404)
    qs = Project.objects.filter(status__in=["EN_ATTENTE", "PUBLIE"]).exclude(pk=project.pk).select_related("developer").defer("icon_data")
    if project.category: qs = qs.filter(category__iexact=project.category)
    items = list(qs.order_by("-featured", "-created_at")[:8])
    if len(items) < 4:
        extra = Project.objects.filter(status__in=["EN_ATTENTE", "PUBLIE"]).exclude(pk=project.pk).exclude(pk__in=[p.pk for p in items]).select_related("developer").defer("icon_data").order_by("-featured", "-created_at")[:4-len(items)]
        items.extend(extra)
    return ok([project_list_public(p) for p in items])

@csrf_exempt
def public_developer(request, developer_id):
    if request.method != "GET": return err("Méthode non autorisée.", 405)
    user = User.objects.filter(pk=developer_id, is_active=True).first()
    if not user: return err("Développeur introuvable.", 404)
    projects = Project.objects.filter(developer=user, status__in=["EN_ATTENTE", "PUBLIE"]).select_related("developer").defer("icon_data").order_by("-created_at")
    return ok({"id": user.pk, "name": user.get_full_name() or user.username, "projects_count": projects.count(), "projects": [project_list_public(p) for p in projects[:30]]})

@csrf_exempt
def project_favorite(request, slug):
    if request.method not in {"GET", "POST", "DELETE"}:
        return err("Méthode non autorisée.", 405)
    project = Project.objects.filter(slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]).first()
    if not project:
        return err("Projet introuvable.", 404)
    if _rate_limited(request, "project_favorite_ip", 600, 60, identity=slug):
        return err("Trop de modifications de favoris depuis cette connexion.", 429)
    if _rate_limited(request, "project_favorite", 60, 60, identity=f"{slug}:{_visitor_rate_identity(request)}"):
        return err("Trop de modifications de favoris. Réessayez plus tard.", 429)
    visitor = _visitor_from_request(request)
    if not visitor:
        return err("Identité visiteur invalide. Rechargez la page.", 401)
    favorite = Favorite.objects.filter(project=project, visitor=visitor).first()
    is_favorite = favorite is not None
    if request.method == "POST":
        if favorite:
            favorite.delete()
            is_favorite = False
        else:
            Favorite.objects.create(project=project, visitor=visitor)
            is_favorite = True
    elif request.method == "DELETE" and favorite:
        favorite.delete()
        is_favorite = False
    count = Favorite.objects.filter(project=project).count()
    return ok({"is_favorite": is_favorite, "favorites_count": count})

@csrf_exempt
def project_comments(request, slug):
    project = Project.objects.filter(slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]).first()
    if not project:
        return err("Projet introuvable.", 404)

    if request.method == "GET":
        comments = project.comments.filter(is_hidden=False).order_by("-created_at")
        return ok([{
            "id": comment.id,
            "author_name": comment.author_name,
            "content": comment.content,
            "created_at": comment.created_at.isoformat(),
        } for comment in comments])

    if request.method == "POST":
        body = json_body(request)
        name = str(body.get("author_name", "")).strip()
        content = str(body.get("content", "")).strip()
        if not name or not content:
            return err("Nom et commentaire requis.")
        if len(name) > 100:
            return err("Le nom ne doit pas dépasser 100 caractères.")
        if len(content) > 2000:
            return err("Le commentaire est trop long.")
        if _rate_limited(request, "project_comment_ip", 100, 3600, identity=slug):
            return err("Trop de commentaires envoyés depuis cette connexion.", 429)
        if _rate_limited(request, "project_comment", 10, 3600, identity=f"{slug}:{_visitor_rate_identity(request)}"):
            return err("Trop de commentaires envoyés. Réessayez plus tard.", 429)
        visitor = _visitor_from_request(request)
        if not visitor:
            return err("Identité visiteur invalide. Rechargez la page.", 401)
        if Comment.objects.filter(project=project, visitor=visitor).count() >= 3:
            return err("Vous avez atteint la limite de 3 commentaires pour ce projet.", 429)

        manage_token = secrets.token_urlsafe(32)
        comment = Comment.objects.create(
            project=project, visitor=visitor, author_name=name, content=content,
            manage_token_hash=hash_token(manage_token),
        )
        return ok({
            "id": comment.id, "author_name": comment.author_name,
            "content": comment.content, "created_at": comment.created_at.isoformat(),
            "manage_token": manage_token,
        }, 201)

    return err("Méthode non autorisée.", 405)


def comment_report(request, slug, comment_id):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    if _rate_limited(request, "comment_report_ip", 100, 3600, identity=f"{slug}:{comment_id}"):
        return err("Trop de signalements depuis cette connexion.", 429)
    if _rate_limited(request, "comment_report", 10, 3600, identity=f"{slug}:{comment_id}:{_visitor_rate_identity(request)}"):
        return err("Trop de signalements. Réessayez plus tard.", 429)
    comment = Comment.objects.select_related("project").filter(
        id=comment_id, project__slug=slug, is_hidden=False,
        project__status__in=["EN_ATTENTE", "PUBLIE"],
    ).first()
    if not comment:
        return err("Commentaire introuvable.", 404)
    visitor = _visitor_from_request(request)
    if not visitor:
        return err("Identité visiteur invalide. Rechargez la page.", 401)
    if CommentReport.objects.filter(comment=comment, visitor=visitor).exists():
        return err("Vous avez déjà signalé ce commentaire.", 409)
    body = json_body(request)
    reason = str(body.get("reason", "")).strip()
    description = str(body.get("description", "")).strip()
    if not reason:
        return err("Motif du signalement requis.")
    CommentReport.objects.create(
        comment=comment, visitor=visitor, reason=reason[:200],
        description=description[:2000],
    )
    # Un signalement déclenche une modération, jamais un masquage automatique.
    return ok({"message": "Signalement transmis à l'administration."}, 201)


def project_comment_detail(request, slug, comment_id):
    if request.method not in {"PATCH", "DELETE"}:
        return err("Méthode non autorisée.", 405)

    comment = Comment.objects.select_related("project").filter(
        id=comment_id,
        project__slug=slug,
        project__status__in=["EN_ATTENTE", "PUBLIE"],
    ).first()
    if not comment:
        return err("Commentaire introuvable.", 404)

    supplied_token = request.headers.get("X-Comment-Token", "").strip()
    if not supplied_token or not comment.manage_token_hash:
        return err("Vous n'êtes pas autorisé à gérer ce commentaire.", 403)
    if not secrets.compare_digest(comment.manage_token_hash, hash_token(supplied_token)):
        return err("Vous n'êtes pas autorisé à gérer ce commentaire.", 403)

    if request.method == "DELETE":
        comment.delete()
        return HttpResponse(status=204)

    body = json_body(request)
    name = str(body.get("author_name", comment.author_name)).strip()
    content = str(body.get("content", comment.content)).strip()
    if not name or not content:
        return err("Nom et commentaire requis.")
    if len(name) > 100:
        return err("Le nom ne doit pas dépasser 100 caractères.")
    if len(content) > 2000:
        return err("Le commentaire est trop long.")

    comment.author_name = name
    comment.content = content
    comment.save(update_fields=["author_name", "content"])
    return ok({
        "id": comment.id,
        "author_name": comment.author_name,
        "content": comment.content,
        "created_at": comment.created_at.isoformat(),
    })


@csrf_exempt
def project_reports(request,slug):
    p=Project.objects.filter(slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]).first()
    if not p: return err("Projet introuvable.",404)
    if request.method!="POST": return err("Méthode non autorisée.",405)
    visitor = _visitor_from_request(request)
    if not visitor:
        return err("Identité visiteur invalide. Rechargez la page.", 401)
    if _rate_limited(request, "project_report_ip", 10, 3600, identity=slug):
        return err("Trop de signalements depuis cette connexion. Réessayez plus tard.", 429)
    if _rate_limited(request, "project_report_visitor", 2, 3600, identity=f"{slug}:{visitor.pk}"):
        return err("Vous avez déjà signalé ce projet récemment.", 429)
    b=json_body(request); reason=str(b.get("reason","")).strip(); description=str(b.get("description","")).strip()
    if not reason: return err("Motif requis.")
    if len(reason) > 200 or len(description) > 1000:
        return err("Le motif ou la description dépasse la longueur autorisée.")
    r=Report.objects.create(project=p,reason=reason,description=description)
    return ok({"id":r.id,"message":"Signalement enregistré."},201)

@csrf_exempt
def project_event(request,slug):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    p=Project.objects.filter(slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]).first()
    if not p: return err("Projet introuvable.",404)
    typ=json_body(request).get("type")
    if typ not in {"view","visit_click","install"}: return err("Type d'événement invalide.")
    visitor = _visitor_from_request(request)
    if not visitor: return err("Identité visiteur invalide. Rechargez la page.", 401)
    if _rate_limited(request, "project_event_ip", 30, 60, identity=f"{slug}:{typ}"):
        return err("Trop d'événements depuis cette connexion.", 429)
    if _rate_limited(request, "project_event", 5, 60, identity=f"{slug}:{typ}:{_visitor_rate_identity(request)}"):
        return err("Trop d'événements. Réessayez plus tard.", 429)
    dedupe_seconds = 1800 if typ == "view" else 60
    recent = Event.objects.filter(
        project=p, visitor=visitor, type=typ,
        created_at__gte=timezone.now() - timedelta(seconds=dedupe_seconds),
    ).exists()
    if recent:
        return ok({"message": "Événement déjà comptabilisé récemment.", "recorded": False})
    Event.objects.create(project=p, visitor=visitor, type=typ)
    return ok({"message":"Événement enregistré.", "recorded": True},201)


def _email_code_digest(user, purpose, code):
    """HMAC du code : le code à 6 chiffres n'est jamais conservé en clair."""
    message = f"{user.pk}:{purpose}:{code}".encode("utf-8")
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def send_transactional_email(to_email, subject, text_content, html_content):
    """Envoi Brevo (API HTTPS), avec SMTP en solution de secours si configuré."""
    api_key = getattr(settings, "BREVO_API_KEY", "")
    provider = getattr(settings, "EMAIL_PROVIDER", "brevo")

    if provider == "brevo" and api_key:
        payload = {
            "sender": {
                "name": settings.EMAIL_FROM_NAME,
                "email": settings.DEFAULT_FROM_EMAIL,
            },
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": text_content,
            "htmlContent": html_content,
        }
        request = Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=12) as response:
                return 200 <= response.status < 300
        except Exception:
            # Ne jamais exposer la clé ni le détail de l'erreur du fournisseur.
            return False

    # En local, le backend console permet de vérifier le contenu sans envoyer
    # de vrai e-mail. En production, SMTP reste utilisable si explicitement choisi.
    if provider == "smtp" and getattr(settings, "EMAIL_HOST", ""):
        from django.core.mail import send_mail
        try:
            return send_mail(
                subject,
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [to_email],
                html_message=html_content,
                fail_silently=False,
            ) == 1
        except Exception:
            return False

    if settings.DEBUG and not api_key:
        from django.core.mail import send_mail
        try:
            return send_mail(
                subject,
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [to_email],
                html_message=html_content,
                fail_silently=False,
            ) == 1
        except Exception:
            return False

    return False


def _issue_email_code(user, purpose):
    """Crée et envoie un code unique avec expiration et délai anti-renvoi."""
    now = timezone.now()
    existing = EmailCode.objects.filter(user=user, purpose=purpose).first()
    cooldown = getattr(settings, "EMAIL_RESEND_COOLDOWN_SECONDS", 60)
    if existing and existing.last_sent_at:
        elapsed = (now - existing.last_sent_at).total_seconds()
        if elapsed < cooldown:
            return False, "cooldown"

    code = f"{secrets.randbelow(1000000):06d}"
    if purpose == "verification":
        ttl = settings.EMAIL_VERIFICATION_CODE_TTL_MINUTES
        subject = "WEB STORE — Vérification de votre adresse e-mail"
        purpose_label = "vérifier votre adresse e-mail"
    else:
        ttl = settings.EMAIL_PASSWORD_RESET_CODE_TTL_MINUTES
        subject = "WEB STORE — Réinitialisation du mot de passe"
        purpose_label = "réinitialiser votre mot de passe"

    text_content = (
        f"Votre code WEB STORE pour {purpose_label} est : {code}\n\n"
        f"Ce code expire dans {ttl} minute(s). "
        "Ne le partagez avec personne."
    )
    html_content = (
        '<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;'
        'padding:24px;color:#17221b">'
        '<h2 style="color:#16A34A">WEB STORE</h2>'
        f'<p>Utilisez ce code pour {purpose_label} :</p>'
        '<p style="font-size:30px;font-weight:700;letter-spacing:7px;'
        f'color:#16A34A">{code}</p>'
        f'<p>Ce code expire dans {ttl} minute(s).</p>'
        '<p>Ne le partagez avec personne.</p></div>'
    )

    if not send_transactional_email(user.email, subject, text_content, html_content):
        return False, "send_failed"

    EmailCode.objects.update_or_create(
        user=user,
        purpose=purpose,
        defaults={
            "code_hash": _email_code_digest(user, purpose, code),
            "expires_at": now + timedelta(minutes=ttl),
            "attempts": 0,
            "last_sent_at": now,
        },
    )
    return True, code


def _check_email_code(user, purpose, code):
    """Vérifie un code en conservant le verrouillage jusqu'à son expiration."""
    with transaction.atomic():
        record = EmailCode.objects.select_for_update().filter(
            user=user, purpose=purpose
        ).first()
        if not record:
            return False, "invalid"
        if record.expires_at <= timezone.now():
            record.delete()
            return False, "expired"
        # Ne pas supprimer le record au verrouillage : sa suppression permettrait
        # de recommencer immédiatement une série de tentatives.
        if record.attempts >= settings.EMAIL_CODE_MAX_ATTEMPTS:
            return False, "locked"

        expected = _email_code_digest(user, purpose, code)
        if not hmac.compare_digest(record.code_hash, expected):
            record.attempts += 1
            record.save(update_fields=["attempts"])
            if record.attempts >= settings.EMAIL_CODE_MAX_ATTEMPTS:
                return False, "locked"
            return False, "invalid"
        record.delete()
        return True, "ok"


def _generic_reset_response():
    return ok({
        "message": "Si un compte existe pour cette adresse, un code de réinitialisation vient d'être envoyé."
    })


def _pending_registration_digest(pending_id, code):
    material = f"pending-dev:{pending_id}:verification:{code}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), material, hashlib.sha256).hexdigest()


def _send_pending_registration_code(pending, code):
    ttl = settings.EMAIL_VERIFICATION_CODE_TTL_MINUTES
    subject = "WEB STORE — Vérification de votre adresse e-mail"
    text_content = (
        f"Votre code WEB STORE pour vérifier votre adresse e-mail est : {code}\n\n"
        f"Ce code expire dans {ttl} minute(s). Ne le partagez avec personne."
    )
    html_content = (
        '<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;padding:24px;color:#17221b">'
        '<h2 style="color:#16A34A">WEB STORE</h2>'
        '<p>Utilisez ce code pour vérifier votre adresse e-mail :</p>'
        f'<p style="font-size:30px;font-weight:700;letter-spacing:7px;color:#16A34A">{code}</p>'
        f'<p>Ce code expire dans {ttl} minute(s).</p><p>Ne le partagez avec personne.</p></div>'
    )
    return send_transactional_email(pending.email, subject, text_content, html_content)


@csrf_exempt
def dev_register(request):
    """Crée une inscription provisoire ; User n'est créé qu'après validation e-mail."""
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    b = json_body(request)
    full = str(b.get("full_name", "")).strip()[:150]
    username = str(b.get("username", "")).strip()[:150]
    email = str(b.get("email", "")).strip().lower()
    phone = str(b.get("phone", "")).strip()[:40]
    password = b.get("password", "")

    if not all([full, username, email, password]):
        return err("Nom, username, e-mail et mot de passe requis.")
    if not isinstance(password, str):
        return err("Mot de passe invalide.")
    try:
        validate_email(email)
    except ValidationError:
        return err("Adresse e-mail invalide.", 400)
    if User.objects.filter(email__iexact=email).exists():
        return err("Cette adresse e-mail est déjà utilisée.", 409)
    if phone and (DeveloperProfile.objects.filter(phone=phone).exists() or
                  PendingDeveloperRegistration.objects.filter(phone=phone).exclude(email=email).exists()):
        return err("Ce numéro de téléphone est déjà utilisé.", 409)

    if not (settings.BREVO_API_KEY or (
        settings.EMAIL_PROVIDER == "smtp" and getattr(settings, "EMAIL_HOST", "")
    )):
        return err("Le service d'e-mail n'est pas configuré. Contactez l'administration.", 503)

    candidate = User(username="developer", email=email, first_name=full)
    try:
        validate_password(password, user=candidate)
    except ValidationError as exc:
        return err(" ".join(exc.messages), 400)

    now = timezone.now()
    existing = PendingDeveloperRegistration.objects.filter(email=email).first()
    cooldown = getattr(settings, "EMAIL_RESEND_COOLDOWN_SECONDS", 60)
    if existing and (now - existing.last_sent_at).total_seconds() < cooldown:
        return err("Veuillez patienter avant de demander un nouveau code.", 429)

    code = f"{secrets.randbelow(1000000):06d}"
    try:
        if existing:
            pending = existing
            pending.full_name = full
            pending.username = username
            pending.phone = phone
            pending.password_hash = make_password(password)
            pending.code_hash = _pending_registration_digest(pending.pk, code)
            pending.expires_at = now + timedelta(minutes=settings.EMAIL_VERIFICATION_CODE_TTL_MINUTES)
            pending.attempts = 0
            pending.last_sent_at = now
            pending.save()
        else:
            pending = PendingDeveloperRegistration.objects.create(
                full_name=full, username=username, email=email, phone=phone,
                password_hash=make_password(password),
                code_hash="", expires_at=now + timedelta(minutes=settings.EMAIL_VERIFICATION_CODE_TTL_MINUTES),
                attempts=0, last_sent_at=now,
            )
            pending.code_hash = _pending_registration_digest(pending.pk, code)
            pending.save(update_fields=["code_hash"])
    except Exception:
        return err("Impossible de préparer l'inscription. Réessayez.", 500)

    if not _send_pending_registration_code(pending, code):
        pending.delete()
        return err("L'envoi de l'e-mail a échoué. Réessayez plus tard.", 503)

    return ok({
        "message": "Vérifiez votre adresse e-mail avec le code envoyé. Aucun compte n'est encore créé.",
        "verification_required": True,
    }, 201)


@csrf_exempt
def dev_verify_email(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    b = json_body(request)
    email = str(b.get("email", "")).strip().lower()
    code = str(b.get("code", "")).strip()
    if not re.fullmatch(r"\d{6}", code):
        return err("Code invalide.", 400)

    # Nouveau flux : aucun User n'est créé avant validation du code.
    profile_status = "ACTIF"
    with transaction.atomic():
        pending = PendingDeveloperRegistration.objects.select_for_update().filter(email__iexact=email).first()
        if pending:
            if pending.expires_at <= timezone.now():
                pending.delete()
                return err("Code expiré. Recommencez votre inscription.", 400)
            if pending.attempts >= settings.EMAIL_CODE_MAX_ATTEMPTS:
                return err("Trop de tentatives. Recommencez votre inscription.", 429)
            expected = _pending_registration_digest(pending.pk, code)
            if not hmac.compare_digest(pending.code_hash, expected):
                pending.attempts += 1
                pending.save(update_fields=["attempts"])
                if pending.attempts >= settings.EMAIL_CODE_MAX_ATTEMPTS:
                    return err("Trop de tentatives. Recommencez votre inscription.", 429)
                return err("Code invalide.", 400)
            if User.objects.filter(email__iexact=pending.email).exists():
                pending.delete()
                return err("Cette adresse e-mail est déjà utilisée. Recommencez avec une autre adresse.", 409)
            if DeveloperProfile.objects.filter(phone=pending.phone).exclude(phone="").exists():
                pending.delete()
                return err("Ce numéro de téléphone est déjà utilisé.", 409)
            # Le username Django reste un identifiant technique unique. Le username public
            # est conservé dans DeveloperProfile et peut être partagé entre développeurs.
            user = User(username=f"dev_{uuid.uuid4().hex}", email=pending.email, first_name=pending.full_name)
            user.password = pending.password_hash
            user.save(force_insert=True)
            DeveloperProfile.objects.create(user=user, phone=pending.phone, public_username=pending.username, email_verified=True)
            pending.delete()
        else:
            # Compatibilité temporaire avec les inscriptions commencées avant cette mise à jour.
            user = User.objects.filter(email__iexact=email).first()
            if not user or not hasattr(user, "developer_profile"):
                return err("Code invalide.", 400)
            profile = user.developer_profile
            profile_status = profile.status
            if profile.email_verified:
                return ok({"message": "E-mail déjà vérifié."})
            valid, reason = _check_email_code(user, "verification", code)
            if not valid:
                if reason == "expired":
                    return err("Code expiré. Demandez un nouveau code.", 400)
                if reason == "locked":
                    return err("Trop de tentatives. Demandez un nouveau code.", 429)
                return err("Code invalide.", 400)
            profile.email_verified = True
            profile.verification_code = ""
            profile.save(update_fields=["email_verified", "verification_code"])

    if not user.is_active or profile_status != "ACTIF":
        return err("Votre compte n'est pas actif.", 403)
    return ok({
        "message": "E-mail vérifié.",
        "token": issue_token(user, "dev"),
        "user": {"id": user.id, "username": user.developer_profile.public_username or user.username, "email": user.email,
                 "full_name": user.get_full_name()},
    })


@csrf_exempt
def dev_resend_code(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    email = str(json_body(request).get("email", "")).strip().lower()
    pending = PendingDeveloperRegistration.objects.filter(email__iexact=email).first()
    if pending:
        now = timezone.now()
        cooldown = getattr(settings, "EMAIL_RESEND_COOLDOWN_SECONDS", 60)
        if (now - pending.last_sent_at).total_seconds() < cooldown:
            return err("Veuillez patienter avant de demander un nouveau code.", 429)
        code = f"{secrets.randbelow(1000000):06d}"
        if not _send_pending_registration_code(pending, code):
            return err("Impossible d'envoyer le code pour le moment.", 503)
        pending.code_hash = _pending_registration_digest(pending.pk, code)
        pending.expires_at = now + timedelta(minutes=settings.EMAIL_VERIFICATION_CODE_TTL_MINUTES)
        pending.attempts = 0
        pending.last_sent_at = now
        pending.save(update_fields=["code_hash", "expires_at", "attempts", "last_sent_at"])
        return ok({"message": "Un nouveau code a été envoyé."})

    # Compatibilité avec les anciennes inscriptions non vérifiées.
    user = User.objects.filter(email__iexact=email).first()
    if user and hasattr(user, "developer_profile") and not user.developer_profile.email_verified:
        sent, result = _issue_email_code(user, "verification")
        if not sent and result == "send_failed":
            return err("Impossible d'envoyer le code pour le moment.", 503)
        if not sent and result == "cooldown":
            return err("Veuillez patienter avant de demander un nouveau code.", 429)
    return ok({"message": "Si une inscription en attente existe, un code a été envoyé."})


LOGIN_MAX_FAILED_ATTEMPTS = 3
LOGIN_BLOCK_SECONDS = 45


def _authenticate_limited(email, kind, password, request=None, allow_inactive=False):
    """Authentifie un compte avec un compteur d'échecs persistant par e-mail/espace."""
    email = email.strip().lower()[:254]
    if not email or not isinstance(password, str):
        return None, False

    ip_material = _client_ip(request) if request is not None else "unknown"
    if request is not None:
        ip_material += ":" + request.META.get("HTTP_USER_AGENT", "")[:200]
    ip_hash = hash_token(ip_material)
    with transaction.atomic():
        attempt, _ = LoginAttemptByIP.objects.get_or_create(email=email, kind=kind, ip_hash=ip_hash)
        attempt = LoginAttemptByIP.objects.select_for_update().get(pk=attempt.pk)
        now = timezone.now()
        if attempt.blocked_until and attempt.blocked_until > now:
            return None, True
        if attempt.blocked_until and attempt.blocked_until <= now:
            attempt.failed_attempts = 0
            attempt.blocked_until = None

        user_record = User.objects.filter(email__iexact=email)
        if kind == "admin":
            user_record = user_record.filter(is_staff=True)
        user_row = user_record.only("username", "password", "is_active").first()
        username = user_row.username if user_row else "__invalid_login__"
        user = None
        if user_row and allow_inactive and not user_row.is_active and check_password(password, user_row.password):
            user = user_row
        else:
            user = authenticate(username=username, password=password)
        if user:
            attempt.delete()
            return user, False

        attempt.failed_attempts += 1
        if attempt.failed_attempts >= LOGIN_MAX_FAILED_ATTEMPTS:
            attempt.blocked_until = now + timedelta(seconds=LOGIN_BLOCK_SECONDS)
        attempt.save(update_fields=["failed_attempts", "blocked_until", "updated_at"])
        return None, False


@csrf_exempt
@require("dev")
def dev_logout(request):
    """Révoque immédiatement le jeton développeur présenté par le client."""
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    authorization = request.headers.get("Authorization", "")
    raw_token = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
    if not raw_token:
        return err("Authentification requise.", 401)
    AuthToken.objects.filter(
        key_hash=hash_token(raw_token),
        user=request.api_user,
        kind="dev",
    ).delete()
    return HttpResponse(status=204)


@csrf_exempt
def dev_login(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    if _rate_limited(request, "dev_login_ip", 20, 300, identity=hash_token(request.META.get("HTTP_USER_AGENT", "")[:200])):
        return err("Trop de tentatives depuis cette connexion. Réessayez plus tard.", 429)
    b = json_body(request)
    if not isinstance(b, dict):
        return err("Données de connexion invalides.", 400)
    email = str(b.get("email", "")).strip()
    user, blocked = _authenticate_limited(email, "dev", b.get("password", ""), request, allow_inactive=True)
    if blocked:
        return err("Trop de tentatives. Réessayez dans 45 secondes.", 429)
    if not user or not hasattr(user, "developer_profile"):
        return err("Identifiants invalides.", 401)
    profile = user.developer_profile
    if not profile.email_verified:
        return err("E-mail non vérifié. Consultez votre boîte de réception et validez votre adresse.", 401)
    if profile.status == "SUSPENDU":
        return ok({"suspended": True, "suspension_reason": profile.suspension_reason or "Aucun motif communiqué.",
                   "appeal_status": profile.appeal_status, "appeal_message": profile.appeal_message})
    if not user.is_active:
        return err("Compte non actif.", 401)
    return ok({
        "token": issue_token(user, "dev"),
        "user": {
            "id": user.id,
            "username": user.developer_profile.public_username or user.username,
            "email": user.email,
            "full_name": user.get_full_name(),
        },
    })


@csrf_exempt
def dev_suspension_appeal(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    if _rate_limited(request, "dev_suspension_appeal", 8, 3600, identity=hash_token(request.META.get("HTTP_USER_AGENT", "")[:200])):
        return err("Trop de tentatives. Réessayez plus tard.", 429)
    data = json_body(request)
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")
    action = str(data.get("action", "")).strip().lower()
    message = str(data.get("message", "")).strip()
    user = User.objects.filter(email__iexact=email, is_staff=False).first()
    if not user or not isinstance(password, str) or not check_password(password, user.password) or not hasattr(user, "developer_profile"):
        return err("Identifiants invalides.", 403)
    profile = user.developer_profile
    if profile.status != "SUSPENDU":
        return err("Ce compte n'est pas suspendu.", 409)
    if action == "accept":
        profile.appeal_status = "ACCEPTEE"
        profile.appeal_message = ""
        profile.appealed_at = timezone.now()
        profile.save(update_fields=["appeal_status", "appeal_message", "appealed_at"])
        return ok({"message": "Vous avez pris connaissance de la suspension."})
    if action == "protest":
        if len(message) < 10:
            return err("Votre justification doit contenir au moins 10 caractères.")
        if len(message) > 5000:
            return err("Votre justification est trop longue.")
        profile.appeal_message = message
        profile.appeal_status = "EN_ATTENTE"
        profile.appealed_at = timezone.now()
        profile.save(update_fields=["appeal_message", "appeal_status", "appealed_at"])
        return ok({"message": "Votre contestation a été transmise à l'administration."})
    return err("Action invalide.")


@csrf_exempt
def dev_password_reset(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    email = str(json_body(request).get("email", "")).strip().lower()
    user = User.objects.filter(email__iexact=email).first()
    if user and hasattr(user, "developer_profile"):
        sent, result = _issue_email_code(user, "password_reset")
        if sent and settings.DEBUG:
            return ok({
                "message": "Si un compte existe pour cette adresse, un code de réinitialisation vient d'être envoyé.",
                "reset_code": result,
            })
    return _generic_reset_response()


@csrf_exempt
def dev_password_reset_confirm(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    b = json_body(request)
    email = str(b.get("email", "")).strip().lower()
    code = str(b.get("code", "")).strip()
    password = b.get("new_password", "")
    if not isinstance(password, str) or len(password) < 8:
        return err("Le mot de passe doit contenir au moins 8 caractères.")

    user = User.objects.filter(email__iexact=email).first()
    if not user or not hasattr(user, "developer_profile"):
        return err("Code invalide.", 400)
    valid, reason = _check_email_code(user, "password_reset", code)
    if not valid:
        if reason == "expired":
            return err("Code expiré. Demandez une nouvelle réinitialisation.", 400)
        if reason == "locked":
            return err("Trop de tentatives. Demandez un nouveau code.", 429)
        return err("Code invalide.", 400)

    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        return err(" ".join(exc.messages), 400)

    user.set_password(password)
    user.save(update_fields=["password"])
    user.api_tokens.all().delete()
    return ok({"message": "Mot de passe mis à jour."})

@require("dev")
def dev_me(request):
    u = request.api_user
    p = u.developer_profile
    if request.method == "POST":
        body = json_body(request)
        if not isinstance(body, dict):
            return err("Données de profil invalides.", 400)
        full_name = str(body.get("full_name", u.get_full_name())).strip()
        phone = str(body.get("phone", p.phone)).strip()
        if len(full_name) > 150 or len(phone) > 40:
            return err("Nom ou téléphone trop long.", 400)
        avatar_data = body.get("avatar_data", p.avatar_data)
        if avatar_data != p.avatar_data:
            if avatar_data:
                try:
                    avatar_data = validate_icon_data(avatar_data)
                except ValueError as exc:
                    return err(str(exc), 400)
                if len(avatar_data) > 420000:
                    return err("La photo de profil est trop volumineuse. Réduisez sa taille.", 400)
            else:
                avatar_data = ""
        parts = full_name.split(" ", 1)
        u.first_name = parts[0] if parts else ""
        u.last_name = parts[1] if len(parts) > 1 else ""
        u.save(update_fields=["first_name", "last_name"])
        p.phone = phone
        p.avatar_data = avatar_data
        p.save(update_fields=["phone", "avatar_data"])
    elif request.method != "GET":
        return err("Méthode non autorisée.", 405)
    return ok({"id":u.id,"full_name":u.get_full_name(),"username":u.developer_profile.public_username or u.username,"email":u.email,
               "phone":p.phone,"avatar_data":p.avatar_data,"status":p.status,"email_verified":p.email_verified})


@require("dev")
def dev_password_change(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    body = json_body(request)
    current_password = str(body.get("current_password", ""))
    new_password = str(body.get("new_password", ""))
    confirm_password = str(body.get("confirm_password", ""))
    user = request.api_user
    if not user.check_password(current_password):
        return err("Le mot de passe actuel est incorrect.", 400)
    if new_password != confirm_password:
        return err("Les nouveaux mots de passe ne correspondent pas.", 400)
    if len(new_password) < 8:
        return err("Le nouveau mot de passe doit contenir au moins 8 caractères.", 400)
    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        return err(" ".join(exc.messages), 400)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    AuthToken.objects.filter(user=user, kind="dev").delete()
    return ok({"message":"Mot de passe modifié. Reconnectez-vous avec votre nouveau mot de passe."})

@require("dev")
def dev_dashboard(request):
    u=request.api_user; qs=Project.objects.filter(developer=u)
    return ok({"published_count":qs.filter(status="PUBLIE").count(),"pending_count":qs.filter(status="EN_ATTENTE").count(),
               "total_views":Event.objects.filter(project__developer=u,type="view").count(),
               "unread_messages":Message.objects.filter(recipient=u,read=False).count(),
               "recent_activity":[]})

def dev_project_payload(p):
    d=project_public(p); d["slug"]=p.slug; return d

@require("dev")
def dev_projects(request):
    u=request.api_user
    if request.method=="GET": return ok([dev_project_payload(p) for p in Project.objects.filter(developer=u).order_by("-created_at")])
    if request.method=="POST":
        b=json_body(request)
        return create_dev_project(u,b)
    return err("Méthode non autorisée.",405)

def unique_slug(name):
    base=slugify(name)[:150] or "projet"; s=base; i=2
    while Project.objects.filter(slug=s).exists(): s=f"{base}-{i}"; i+=1
    return s

def validate_icon_data(value, max_size=500 * 1024):
    if not value:
        return ""
    if not isinstance(value, str) or not value.startswith("data:image/"):
        raise ValueError("L'icône doit être une image.")
    header, separator, encoded = value.partition(",")
    if not separator:
        raise ValueError("Icône invalide.")
    mime = header[5:].split(";")[0].lower()
    allowed = {"image/png", "image/jpeg", "image/webp", "image/gif"}
    if mime not in allowed:
        raise ValueError("Format d'icône non pris en charge.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception:
        raise ValueError("Icône invalide.")
    if len(raw) > max_size:
        limit_mb = max_size / (1024 * 1024)
        limit_label = f"{int(limit_mb)} Mo" if limit_mb.is_integer() else f"{max_size // 1024} Ko"
        raise ValueError("L’icône dépasse la limite serveur de 5 Mo. Pour de meilleures performances, privilégiez une icône de 2 Mo maximum.")
    signatures = {
    "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
    "image/gif": raw.startswith((b"GIF87a", b"GIF89a")),
    "image/webp": len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP",
}
    if not signatures[mime]:
        raise ValueError("Le contenu de l'icône ne correspond pas à son format.")
    return value

def create_dev_project(u,b):
    name=str(b.get("name","")).strip(); url=str(b.get("url","")).strip()
    if not name or not url: return err("Nom et URL requis.")
    if not valid_project_url(url): return err("L'URL doit commencer par http:// ou https://.")
    project_type = b.get("type", "WEB")
    if not isinstance(project_type, str) or project_type not in {"WEB", "PWA"}: return err("Type de projet invalide.")
    try:
        icon_data=validate_icon_data(b.get("icon_data",""), max_size=5 * 1024 * 1024)
    except ValueError as exc:
        return err(str(exc))
    pwa_verified=verify_pwa_url(url)
    p=Project.objects.create(developer=u,name=name,slug=unique_slug(name),description=str(b.get("description","")).strip(),
        url=url,type=project_type,category=str(b.get("category","")).strip(),tags=b.get("tags",[]),
        icon_data=icon_data,pwa_verified=pwa_verified,status="EN_ATTENTE")
    return ok(dev_project_payload(p),201)

@require("dev")
def dev_project_detail(request,project_id):
    p=Project.objects.filter(id=project_id,developer=request.api_user).first()
    if not p: return err("Projet introuvable.",404)
    if request.method=="GET": return ok(dev_project_payload(p))
    if request.method=="PUT":
        b=json_body(request)
        for k in ["name","description","url","category","type","tags"]:
            if k in b: setattr(p,k,b[k])
        if "name" in b: p.name=str(b["name"]).strip()
        if "type" in b and (not isinstance(b["type"], str) or b["type"] not in {"WEB", "PWA"}):
            return err("Type de projet invalide.")
        if "url" in b and not valid_project_url(str(b.get("url", "")).strip()):
            return err("L'URL doit commencer par http:// ou https://.")
        if "icon_data" in b:
            try:
                new_icon=validate_icon_data(b.get("icon_data",""), max_size=5 * 1024 * 1024)
            except ValueError as exc:
                return err(str(exc))
            if new_icon:
                p.icon_data=new_icon
        if "url" in b:
            p.pwa_verified=verify_pwa_url(str(b.get("url","")).strip())
        p.save()
        return ok(dev_project_payload(p))
    if request.method=="DELETE":
        p.delete(); return ok(None,204)
    return err("Méthode non autorisée.",405)

def _stats_since(request):
    """Retourne la borne de début demandée, avec dates personnalisées inclusives."""
    period = (request.GET.get("period") or "total").strip()
    now = timezone.now()
    if period == "7": return now - timedelta(days=7), period
    if period == "30": return now - timedelta(days=30), period
    if period == "90": return now - timedelta(days=90), period
    if period == "week": return now - timedelta(days=now.weekday()), period
    if period == "month": return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), period
    if period == "year": return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), period
    if period == "custom":
        start = request.GET.get("start", "")
        end = request.GET.get("end", "")
        try:
            from datetime import date, datetime, time
            start_dt = timezone.make_aware(datetime.combine(date.fromisoformat(start), time.min))
            end_dt = timezone.make_aware(datetime.combine(date.fromisoformat(end), time.max))
            if end_dt < start_dt: return None, "invalid"
            return (start_dt, end_dt), period
        except (TypeError, ValueError):
            return None, "invalid"
    return None, "total"


def _event_stats(projects, since):
    events = Event.objects.filter(project__in=projects)
    if isinstance(since, tuple):
        events = events.filter(created_at__range=since)
    elif since:
        events = events.filter(created_at__gte=since)
    return {
        "sheet_views": events.filter(type="view").count(),
        "visit_clicks": events.filter(type="visit_click").count(),
        "install_clicks": events.filter(type="install").count(),
    }


@require("dev")
def dev_project_stats(request, project_id):
    owned = Project.objects.filter(developer=request.api_user)
    if str(project_id).isdigit():
        p = owned.filter(id=int(project_id)).first()
    else:
        p = owned.filter(slug=str(project_id)).first()
    if not p:
        return err("Projet introuvable ou n'appartenant pas à ce compte développeur.", 404)
    since, period = _stats_since(request)
    if period == "invalid": return err("Période personnalisée invalide.",400)
    data = _event_stats([p], since)
    event_qs = Event.objects.filter(project=p)
    if isinstance(since, tuple):
        event_qs = event_qs.filter(created_at__range=since)
    elif since:
        event_qs = event_qs.filter(created_at__gte=since)
    grouped = event_qs.annotate(day=TruncDate("created_at")).values("day", "type").annotate(total=Count("id")).order_by("day")
    series_map = {}
    for item in grouped:
        day = item["day"].isoformat()
        series_map.setdefault(day, {"date": day, "view": 0, "visit_click": 0, "install": 0})
        if item["type"] in {"view", "visit_click", "install"}:
            series_map[day][item["type"]] = item["total"]
    data["series"] = list(series_map.values())
    favorites = Favorite.objects.filter(project=p)
    if isinstance(since, tuple): favorites = favorites.filter(created_at__range=since)
    elif since: favorites = favorites.filter(created_at__gte=since)
    comments = p.comments.all()
    if isinstance(since, tuple): comments = comments.filter(created_at__range=since)
    elif since: comments = comments.filter(created_at__gte=since)
    data.update({
        "project_name": p.name, "period": period,
        "favorites_count": favorites.count(),
        "comments_count": comments.count(),
        "installs": data["install_clicks"] if p.type == "PWA" else None,
        "confirmed_installs": None,
        "install_note": "Les clics sur « Installer » sont comptabilisés. Une installation réelle sur un site externe ne peut pas être confirmée par WEB STORE.",
    })
    return ok(data)


@admin_only
def admin_project_analytics(request):
    if request.method != "GET": return err("Méthode non autorisée.",405)
    since, period = _stats_since(request)
    if period == "invalid": return err("Période personnalisée invalide.",400)
    events = Event.objects.all()
    if isinstance(since, tuple): events = events.filter(created_at__range=since)
    elif since: events = events.filter(created_at__gte=since)
    favorites = Favorite.objects.all()
    if isinstance(since, tuple): favorites = favorites.filter(created_at__range=since)
    elif since: favorites = favorites.filter(created_at__gte=since)
    projects = Project.objects.filter(status="PUBLIE")
    rows=[]
    for p in projects.select_related("developer"):
        ev=events.filter(project=p)
        rows.append({
            "id":p.id, "name":p.name, "slug":p.slug,
            "developer":p.developer.get_full_name() or p.developer.username,
            "type":p.type, "category":p.category,
            "views":ev.filter(type="view").count(),
            "visits":ev.filter(type="visit_click").count(),
            "install_clicks":ev.filter(type="install").count(),
            "favorites":favorites.filter(project=p).count(),
        })
    rows.sort(key=lambda x:(x["views"],x["visits"],x["favorites"]), reverse=True)
    return ok({
        "period":period, "projects_count":len(rows),
        "totals":{
            "views":sum(x["views"] for x in rows),
            "visits":sum(x["visits"] for x in rows),
            "install_clicks":sum(x["install_clicks"] for x in rows),
            "favorites":sum(x["favorites"] for x in rows),
        },
        "most_viewed":sorted(rows,key=lambda x:x["views"],reverse=True)[:20],
        "most_visited":sorted(rows,key=lambda x:x["visits"],reverse=True)[:20],
        "most_favorited":sorted(rows,key=lambda x:x["favorites"],reverse=True)[:20],
        "most_installed":sorted(rows,key=lambda x:x["install_clicks"],reverse=True)[:20],
        "projects":rows,
        "install_note":"Les installations affichées sont des clics sur « Installer », pas des installations réelles confirmées."
    })

@require("dev")
def dev_project_comments(request,project_id):
    p=Project.objects.filter(id=project_id,developer=request.api_user).first()
    if not p: return err("Projet introuvable.",404)
    return ok([{"id":c.id,"author_name":c.author_name,"content":c.content,"created_at":c.created_at.isoformat()} for c in p.comments.filter(is_hidden=False).order_by("-created_at")])

@require("dev")
def dev_messages(request):
    if request.method!="GET": return err("Méthode non autorisée.",405)
    return ok([{"id":m.id,"subject":m.subject,"content":m.content,"read":m.read,"created_at":m.created_at.isoformat(),"sender_name":m.sender.get_full_name() or m.sender.username,"sender_email":m.sender.email} for m in Message.objects.filter(recipient=request.api_user).select_related("sender").order_by("-created_at")])

@require("dev")
def dev_message_detail(request,message_id):
    m=Message.objects.filter(id=message_id,recipient=request.api_user).first()
    if not m: return err("Message introuvable.",404)
    if request.method=="GET":
        replies = [{
            "id": r.id,
            "content": r.content,
            "created_at": r.created_at.isoformat(),
            "sender_name": r.sender.get_full_name() or r.sender.username,
            "is_mine": r.sender_id == request.api_user.id,
        } for r in m.replies.select_related("sender").order_by("created_at")]
        return ok({
            "id": m.id, "subject": m.subject, "content": m.content,
            "read": m.read, "created_at": m.created_at.isoformat(),
            "sender_name": m.sender.get_full_name() or m.sender.username,
            "sender_email": m.sender.email, "replies": replies,
        })
    if request.method=="PATCH":
        if json_body(request).get("read") is True: m.read=True;m.save(update_fields=["read"])
        return ok({"message":"Message mis à jour."})
    if request.method=="DELETE":
        m.delete()
        return ok({"message":"Message supprimé."})
    return err("Méthode non autorisée.",405)

@require("dev")
def dev_message_reply(request,message_id):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    m=Message.objects.filter(id=message_id,recipient=request.api_user).first()
    if not m: return err("Message introuvable.",404)
    b = json_body(request)
    raw_content = b.get("content", "")
    if not isinstance(raw_content, str):
        return err("Contenu invalide.")
    content = raw_content.strip()
    if not content:
        return err("Contenu requis.")
    if len(content) > 10000:
        return err("Le message ne doit pas dépasser 10 000 caractères.")
    reply = Message.objects.create(
        sender=request.api_user, recipient=m.sender,
        subject=("Re: " + m.subject)[:200], content=content, parent=m,
    )
    return ok({"id":reply.id},201)

@csrf_exempt
@admin_only
def admin_logout(request):
    """Révoque immédiatement le jeton administrateur présenté par le client."""
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    authorization = request.headers.get("Authorization", "")
    raw_token = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
    if not raw_token:
        return err("Authentification requise.", 401)
    AuthToken.objects.filter(
        key_hash=hash_token(raw_token),
        user=request.api_user,
        kind="admin",
    ).delete()
    return HttpResponse(status=204)


# --- Authentification forte de l'administration (WebAuthn / Passkeys) ---
ADMIN_WEBAUTHN_RP_ID = "store-by-dekal.onrender.com"
ADMIN_WEBAUTHN_ORIGIN = "https://store-by-dekal.onrender.com"
ADMIN_WEBAUTHN_RP_NAME = "WEB STORE Administration"
ADMIN_WEBAUTHN_TTL = timedelta(minutes=5)


def _b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64u(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _webauthn_imports():
    from webauthn import (generate_registration_options, verify_registration_response,
                         generate_authentication_options, verify_authentication_response,
                         options_to_json)
    from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, AuthenticatorAttachment,
        ResidentKeyRequirement, UserVerificationRequirement, PublicKeyCredentialDescriptor)
    return (generate_registration_options, verify_registration_response,
            generate_authentication_options, verify_authentication_response, options_to_json,
            AuthenticatorSelectionCriteria, AuthenticatorAttachment, ResidentKeyRequirement,
            UserVerificationRequirement, PublicKeyCredentialDescriptor)


def _admin_webauthn_ready():
    return AdminPasskey.objects.exists()


def _challenge_row(user, purpose, challenge="", token_hash=""):
    AdminAuthChallenge.objects.filter(expires_at__lte=timezone.now()).delete()
    return AdminAuthChallenge.objects.create(
        user=user, purpose=purpose, challenge=challenge, token_hash=token_hash,
        expires_at=timezone.now() + ADMIN_WEBAUTHN_TTL,
    )


def _admin_mfa_row(request):
    body = json_body(request)
    token = str(body.get("mfa_token", ""))
    if not token or len(token) > 160:
        return None, body
    row = AdminAuthChallenge.objects.select_related("user").filter(
        token_hash=hash_token(token), purpose="login", expires_at__gt=timezone.now()
    ).first()
    return row, body


@csrf_exempt
@founder_only
def admin_administrators(request):
    """API de création/liste des comptes ADMIN, sans interface dashboard."""
    if request.method == "GET":
        rows = User.objects.filter(is_staff=True, admin_role__role=AdminRole.ADMIN).order_by("date_joined")
        return ok([{"id": u.id, "username": u.username, "email": u.email,
                    "full_name": u.get_full_name(), "created_at": u.date_joined.isoformat(),
                    "role": AdminRole.ADMIN}
                   for u in rows])
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    body = json_body(request)
    if not isinstance(body, dict):
        return err("Données invalides.", 400)
    username = str(body.get("username", "")).strip()
    email = str(body.get("email", "")).strip().lower()
    first_name = str(body.get("first_name", "")).strip()
    last_name = str(body.get("last_name", "")).strip()
    password = body.get("password", "")
    if not username or len(username) > 150 or not re.fullmatch(r"[\w.@+-]+", username, re.UNICODE):
        return err("Nom d'utilisateur invalide.", 400)
    if not email or len(email) > 254:
        return err("Adresse e-mail obligatoire et valide.", 400)
    try:
        validate_email(email)
    except ValidationError:
        return err("Adresse e-mail invalide.", 400)
    if not isinstance(password, str) or not password:
        return err("Mot de passe obligatoire.", 400)
    if User.objects.filter(username__iexact=username).exists():
        return err("Ce nom d'utilisateur est déjà utilisé.", 409)
    if User.objects.filter(email__iexact=email).exists():
        return err("Cette adresse e-mail est déjà utilisée.", 409)
    try:
        with transaction.atomic():
            user = User(username=username, email=email, first_name=first_name[:150],
                        last_name=last_name[:150], is_active=True, is_staff=True,
                        is_superuser=False)
            user.set_password(password)
            user.full_clean(exclude=["last_login", "date_joined"])
            validate_password(password, user=user)
            user.save()
            AdminRole.objects.create(user=user, role=AdminRole.ADMIN, created_by=request.api_user)
    except ValidationError as exc:
        return err(" ".join(exc.messages), 400)
    except Exception:
        return err("Impossible de créer cet administrateur. Vérifiez les informations.", 400)
    return ok({"message": "Compte administrateur créé. Transmettez ses identifiants de manière sécurisée.",
               "administrator": {"id": user.id, "username": user.username, "email": user.email,
                                 "full_name": user.get_full_name(), "role": AdminRole.ADMIN}}, 201)


@csrf_exempt
@admin_only
def admin_me(request):
    if request.method != "GET":
        return err("Méthode non autorisée.", 405)
    u = request.api_user
    return ok({"id": u.id, "username": u.username, "email": u.email,
               "full_name": u.get_full_name(), "role": _admin_role_name(u), "passkeys": AdminPasskey.objects.filter(user=u).count()})


@csrf_exempt
@admin_only
def admin_password_change(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    body = json_body(request)
    current = str(body.get("current_password", ""))
    new = str(body.get("new_password", ""))
    confirm = str(body.get("confirm_password", ""))
    user = request.api_user
    if not user.check_password(current):
        return err("Le mot de passe actuel est incorrect.", 400)
    if new != confirm:
        return err("Les nouveaux mots de passe ne correspondent pas.", 400)
    if len(new) < 8:
        return err("Le nouveau mot de passe doit contenir au moins 8 caractères.", 400)
    try:
        validate_password(new, user=user)
    except ValidationError as exc:
        return err(" ".join(exc.messages), 400)
    user.set_password(new)
    user.save(update_fields=["password"])
    AuthToken.objects.filter(user=user, kind="admin").delete()
    return ok({"message": "Mot de passe modifié. Reconnectez-vous."})


@csrf_exempt
@admin_only
def admin_passkey_list(request):
    if request.method != "GET":
        return err("Méthode non autorisée.", 405)
    return ok([{"id": p.id, "device_name": p.device_name or "Appareil autorisé",
                "created_at": p.created_at.isoformat(), "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None}
               for p in AdminPasskey.objects.filter(user=request.api_user)])


@csrf_exempt
@admin_only
def admin_passkey_register_options(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    body = json_body(request)
    if not request.api_user.check_password(str(body.get("current_password", ""))):
        return err("Confirmez votre mot de passe avant d'ajouter une clé biométrique.", 403)
    try:
        (gen_reg, _, _, _, options_json, selection, attachment, resident, verification, descriptor) = _webauthn_imports()
        existing = [descriptor(id=_unb64u(p.credential_id)) for p in AdminPasskey.objects.filter(user=request.api_user)]
        options = gen_reg(
            rp_id=ADMIN_WEBAUTHN_RP_ID, rp_name=ADMIN_WEBAUTHN_RP_NAME,
            user_id=str(request.api_user.pk).encode("utf-8"),
            user_name=request.api_user.email or request.api_user.username,
            user_display_name=request.api_user.get_full_name() or request.api_user.username,
            exclude_credentials=existing,
            authenticator_selection=selection(
                authenticator_attachment=attachment.PLATFORM,
                resident_key=resident.PREFERRED,
                user_verification=verification.REQUIRED,
            ),
        )
        row = _challenge_row(request.api_user, "register", _b64u(options.challenge))
        return ok({"challenge_id": row.id, "options": json.loads(options_json(options))})
    except Exception:
        return err("Impossible de préparer l'enregistrement biométrique. Vérifiez la configuration WebAuthn.", 500)


@csrf_exempt
@admin_only
def admin_passkey_register_verify(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    body = json_body(request)
    row = AdminAuthChallenge.objects.filter(id=body.get("challenge_id"), user=request.api_user,
        purpose="register", expires_at__gt=timezone.now()).first()
    if not row:
        return err("La demande d'enregistrement a expiré. Recommencez.", 400)
    row.delete()
    credential = body.get("credential")
    if not isinstance(credential, dict) or credential.get("authenticatorAttachment") != "platform":
        return err("Utilisez l'empreinte ou la reconnaissance faciale intégrée à cet appareil.", 400)
    try:
        (_, verify_reg, _, _, _, *_) = _webauthn_imports()
        verified = verify_reg(
            credential=credential, expected_challenge=_unb64u(row.challenge),
            expected_rp_id=ADMIN_WEBAUTHN_RP_ID, expected_origin=ADMIN_WEBAUTHN_ORIGIN,
            require_user_verification=True,
        )
        credential_id = _b64u(verified.credential_id)
        if AdminPasskey.objects.filter(credential_id=credential_id).exists():
            return err("Cette clé est déjà enregistrée.", 409)
        device_name = str(body.get("device_name", ""))[:100].strip()
        AdminPasskey.objects.create(user=request.api_user, credential_id=credential_id,
            public_key=_b64u(verified.credential_public_key), sign_count=verified.sign_count,
            device_name=device_name)
        return ok({"message": "Vérification biométrique enregistrée avec succès."}, 201)
    except Exception:
        return err("Vérification biométrique échouée. Réessayez sur cet appareil.", 400)


@csrf_exempt
@admin_only
def admin_passkey_delete(request, passkey_id):
    if request.method != "DELETE":
        return err("Méthode non autorisée.", 405)
    if AdminPasskey.objects.filter(user=request.api_user).count() <= 1:
        return err("Conservez au moins une clé autorisée. Configurez une autre méthode avant de supprimer celle-ci.", 400)
    deleted, _ = AdminPasskey.objects.filter(id=passkey_id, user=request.api_user).delete()
    if not deleted:
        return err("Clé introuvable.", 404)
    return ok({"message": "Clé biométrique révoquée."})


@csrf_exempt
def admin_passkey_login_verify(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    if _rate_limited(request, "admin_passkey_verify", 10, 300):
        return err("Trop de tentatives. Réessayez plus tard.", 429)
    body = json_body(request)
    token = str(body.get("mfa_token", ""))
    if not token or len(token) > 160:
        return err("Cette demande de connexion a expiré. Recommencez.", 401)
    with transaction.atomic():
        row = AdminAuthChallenge.objects.select_for_update().select_related("user").filter(
            token_hash=hash_token(token), purpose="login", expires_at__gt=timezone.now()
        ).first()
        if not row:
            return err("Cette demande de connexion a expiré. Recommencez.", 401)
        if row.attempts >= 5:
            row.delete()
            return err("Trop de tentatives. Recommencez la connexion.", 429)
        try:
            credential = body.get("credential")
            if not isinstance(credential, dict):
                raise ValueError("credential missing")
            credential_id = str(credential.get("id", ""))
            passkey = AdminPasskey.objects.get(user=row.user, credential_id=credential_id)
            (_, _, _, verify_auth, *_) = _webauthn_imports()
            verified = verify_auth(
                credential=credential, expected_challenge=_unb64u(row.challenge),
                expected_rp_id=ADMIN_WEBAUTHN_RP_ID, expected_origin=ADMIN_WEBAUTHN_ORIGIN,
                credential_public_key=_unb64u(passkey.public_key),
                credential_current_sign_count=passkey.sign_count, require_user_verification=True,
            )
            passkey.sign_count = verified.new_sign_count
            passkey.last_used_at = timezone.now()
            passkey.save(update_fields=["sign_count", "last_used_at"])
            user = row.user
            row.delete()
            return ok({"token": issue_token(user, "admin", request), "user": {"id": user.id, "email": user.email,
                       "full_name": user.get_full_name(), "role": _admin_role_name(user)}})
        except Exception:
            row.attempts += 1
            row.save(update_fields=["attempts"])
            return err("Authentification biométrique refusée. Vérifiez votre appareil.", 401)


@csrf_exempt
def admin_passkey_fallback_send(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    if _rate_limited(request, "admin_mfa_email_send", 3, 900):
        return err("Trop de demandes de code. Réessayez plus tard.", 429)
    row, _ = _admin_mfa_row(request)
    if not row:
        return err("Cette demande de connexion a expiré. Recommencez.", 401)
    if row.email_sent_at and row.email_sent_at > timezone.now() - timedelta(seconds=60):
        return err("Attendez une minute avant de demander un nouveau code.", 429)
    code = f"{secrets.randbelow(1000000):06d}"
    row.email_code_hash = hmac.new(settings.SECRET_KEY.encode(), f"{row.user.pk}:admin_mfa:{code}".encode(), hashlib.sha256).hexdigest()
    row.email_sent_at = timezone.now()
    row.attempts = 0
    row.save(update_fields=["email_code_hash", "email_sent_at", "attempts"])
    subject = "Code de secours — WEB STORE Administration"
    text_content = f"Votre code de secours est {code}. Il expire dans 5 minutes. Ne le partagez avec personne."
    html_content = f"<p>Votre code de secours WEB STORE est :</p><p style='font-size:28px;font-weight:bold;letter-spacing:6px'>{code}</p><p>Il expire dans 5 minutes. Ne le partagez avec personne.</p>"
    if not send_transactional_email(row.user.email, subject, text_content, html_content):
        row.email_code_hash = ""
        row.save(update_fields=["email_code_hash"])
        return err("Le code e-mail n'a pas pu être envoyé. Contactez l'administrateur technique.", 503)
    return ok({"message": "Un code temporaire a été envoyé à l'adresse e-mail de l'administrateur."})


@csrf_exempt
def admin_passkey_fallback_verify(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    body = json_body(request)
    token = str(body.get("mfa_token", ""))
    if not token or len(token) > 160:
        return err("Cette demande de connexion a expiré. Recommencez.", 401)
    with transaction.atomic():
        row = AdminAuthChallenge.objects.select_for_update().select_related("user").filter(
            token_hash=hash_token(token), purpose="login", expires_at__gt=timezone.now()
        ).first()
        if not row or not row.email_code_hash:
            return err("Demandez d'abord un code de secours.", 400)
        if not row.email_sent_at or row.email_sent_at < timezone.now() - ADMIN_WEBAUTHN_TTL:
            row.delete()
            return err("Le code de secours a expiré.", 400)
        row.attempts += 1
        code = str(body.get("code", "")).strip()
        expected = hmac.new(settings.SECRET_KEY.encode(), f"{row.user.pk}:admin_mfa:{code}".encode(), hashlib.sha256).hexdigest()
        if row.attempts > 5 or not hmac.compare_digest(expected, row.email_code_hash):
            if row.attempts >= 5:
                row.delete()
            else:
                row.save(update_fields=["attempts"])
            return err("Code incorrect ou expiré.", 401)
        user = row.user
        row.delete()
        return ok({"token": issue_token(user, "admin", request), "user": {"id": user.id, "email": user.email,
                   "full_name": user.get_full_name(), "role": _admin_role_name(user)}})


@csrf_exempt
def admin_login(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    if _rate_limited(request, "admin_login_ip", 20, 300, identity=hash_token(request.META.get("HTTP_USER_AGENT", "")[:200])):
        return err("Trop de tentatives depuis cette connexion. Réessayez plus tard.", 429)
    b = json_body(request)
    if not isinstance(b, dict):
        return err("Données de connexion invalides.", 400)
    email = str(b.get("email", "")).strip().lower()
    user, blocked = _authenticate_limited(email, "admin", b.get("password", ""), request)
    if blocked:
        return err("Trop de tentatives. Réessayez dans 45 secondes.", 429)
    if not user:
        return err("Identifiants invalides.", 401)
    # Alerte dès que l'e-mail et le mot de passe sont corrects, avant MFA et dashboard.
    # L'envoi est non bloquant : Telegram indisponible ne bloque pas la connexion.
    notify_admin_login(user, request)
    passkeys = list(AdminPasskey.objects.filter(user=user))
    if passkeys:
        try:
            (_, _, gen_auth, _, options_json, *_) = _webauthn_imports()
            from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
            options = gen_auth(rp_id=ADMIN_WEBAUTHN_RP_ID,
                allow_credentials=[PublicKeyCredentialDescriptor(id=_unb64u(p.credential_id)) for p in passkeys],
                user_verification=UserVerificationRequirement.REQUIRED)
            raw_mfa = secrets.token_urlsafe(48)
            challenge = _challenge_row(user, "login", _b64u(options.challenge), hash_token(raw_mfa))
            return ok({"mfa_required": True, "mfa_token": raw_mfa,
                       "options": json.loads(options_json(options)), "expires_in": 300})
        except Exception:
            return err("Impossible de préparer la vérification biométrique. Réessayez.", 503)
    raw_mfa = secrets.token_urlsafe(48)
    _challenge_row(user, "login", "", hash_token(raw_mfa))
    return ok({"mfa_required": True, "email_only": True, "mfa_token": raw_mfa,
               "options": None, "expires_in": 300})

@csrf_exempt
@admin_only
def admin_comment_delete(request, comment_id):
    if request.method != "DELETE":
        return err("Méthode non autorisée.", 405)
    comment = Comment.objects.filter(id=comment_id).first()
    if not comment:
        return err("Commentaire introuvable.", 404)
    comment.delete()
    return HttpResponse(status=204)

@admin_only

@csrf_exempt
@admin_only
def admin_comment_restore(request, comment_id):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    comment = Comment.objects.filter(id=comment_id).first()
    if not comment:
        return err("Commentaire introuvable.", 404)
    comment.is_hidden = False
    comment.save(update_fields=["is_hidden"])
    CommentReport.objects.filter(comment=comment, status="OUVERT").update(status="TRAITE")
    return ok({"message": "Commentaire réaffiché après vérification."})

@admin_only
def admin_dashboard(request):
    qs=Project.objects.all()
    pending=qs.filter(status="EN_ATTENTE")
    return ok({"developers_count":DeveloperProfile.objects.filter(email_verified=True, user__is_staff=False).count(),
               "suspended_developers_count":DeveloperProfile.objects.filter(status="SUSPENDU", email_verified=True, user__is_staff=False).count(),
               "visitors_count":Visitor.objects.count(),
               "published_count":qs.filter(status="PUBLIE").count(),
               "pending_count":pending.count(),"open_reports_count":Report.objects.filter(status="OUVERT").count()+CommentReport.objects.filter(status="OUVERT").count(),
               "web_count":qs.filter(type="WEB").count(),"pwa_count":qs.filter(type="PWA").count(),
               "rejected_count":qs.filter(status="REJETE").count(),"suspended_count":qs.filter(status="SUSPENDU").count(),
               "total_project_visits":Event.objects.filter(type="view").count(),
               "total_visit_clicks":Event.objects.filter(type="visit_click").count(),
               "total_installs":Event.objects.filter(type="install").count(),
               "pending_projects":[{"id":p.id,"name":p.name,"developer_name":p.developer.get_full_name() or p.developer.username} for p in pending[:10]]})


@admin_only
def admin_visitor_analytics(request):
    """Données de suivi des visiteurs pour le tableau de bord administrateur."""
    if request.method != "GET":
        return err("Méthode non autorisée.", 405)

    period = request.GET.get("period", "30").strip()
    now = timezone.now()
    if period == "7":
        since = now - timedelta(days=7)
    elif period == "30":
        since = now - timedelta(days=30)
    elif period == "365":
        since = now - timedelta(days=365)
    else:
        since = None

    activities = VisitorActivity.objects.select_related("visitor", "project")
    visitors = Visitor.objects.all()
    if since:
        activities = activities.filter(created_at__gte=since)
        visitors = visitors.filter(last_seen__gte=since)

    total_activities = activities.count()
    searches = activities.filter(activity_type="search")
    categories = activities.filter(activity_type="category")
    project_opens = activities.filter(activity_type="project_open")

    top_categories = list(
        activities.exclude(category="")
        .values("category")
        .annotate(total=Count("id"), visitors=Count("visitor", distinct=True))
        .order_by("-total", "category")[:20]
    )
    top_searches = list(
        searches.exclude(search_query="")
        .values("search_query")
        .annotate(total=Count("id"), visitors=Count("visitor", distinct=True))
        .order_by("-total", "search_query")[:20]
    )
    popular_projects = list(
        project_opens.filter(project__isnull=False)
        .values("project_id", "project__name", "project__slug", "category")
        .annotate(total=Count("id"), visitors=Count("visitor", distinct=True))
        .order_by("-total", "project__name")[:20]
    )
    recent = []
    for item in activities.order_by("-created_at")[:150]:
        recent.append({
            "id": item.id,
            "type": item.activity_type,
            "type_label": {"search": "Recherche", "category": "Catégorie consultée", "project_open": "Projet ouvert"}.get(item.activity_type, item.activity_type),
            "query": item.search_query,
            "category": item.category,
            "results_count": item.results_count,
            "project_name": item.project.name if item.project else "",
            "project_slug": item.project.slug if item.project else "",
            "visitor_id": item.visitor.visitor_id[:10] + "…",
            "created_at": item.created_at.isoformat(),
        })

    return ok({
        "period": period,
        "visitors_count": visitors.count(),
        "activities_count": total_activities,
        "searches_count": searches.count(),
        "zero_result_searches_count": searches.filter(results_count=0).count(),
        "category_views_count": categories.count(),
        "project_opens_count": project_opens.count(),
        "top_categories": top_categories,
        "top_searches": top_searches,
        "popular_projects": popular_projects,
        "recent_activities": recent,
        "recent_limit": 150,
    })

@csrf_exempt
@admin_only
def admin_category_relations(request):
    """Liste et gestion des catégories voisines configurées par l'administrateur."""
    if request.method == "GET":
        rows = CategoryRelation.objects.select_related("category", "neighbor").order_by("category__name", "neighbor__name")
        return ok([{"id": r.id, "category_id": r.category_id, "category": r.category.name,
                    "neighbor_id": r.neighbor_id, "neighbor": r.neighbor.name} for r in rows])
    body = json_body(request)
    if request.method == "POST":
        try:
            category_id = int(body.get("category_id"))
            neighbor_id = int(body.get("neighbor_id"))
        except (TypeError, ValueError):
            return err("Sélectionnez deux catégories valides.")
        if category_id == neighbor_id:
            return err("Une catégorie ne peut pas être sa propre voisine.")
        category = Category.objects.filter(pk=category_id).first()
        neighbor = Category.objects.filter(pk=neighbor_id).first()
        if not category or not neighbor:
            return err("Catégorie introuvable.", 404)
        relation, created = CategoryRelation.objects.get_or_create(category=category, neighbor=neighbor)
        return ok({"id": relation.id, "category": category.name, "neighbor": neighbor.name, "created": created}, 201 if created else 200)
    if request.method == "DELETE":
        try: relation_id = int(body.get("id"))
        except (TypeError, ValueError): return err("Association invalide.")
        deleted, _ = CategoryRelation.objects.filter(pk=relation_id).delete()
        if not deleted: return err("Association introuvable.", 404)
        return ok({"deleted": True})
    return err("Méthode non autorisée.", 405)

@csrf_exempt
def public_recommendations(request):
    """Recommandations basées sur les activités récentes du visiteur."""
    if request.method != "GET": return err("Méthode non autorisée.", 405)
    visitor = _visitor_from_request(request)
    if not visitor: return ok([])
    interests = list(VisitorActivity.objects.filter(visitor=visitor).exclude(category="")
                     .values("category").annotate(score=Count("id")).order_by("-score")[:3])
    if not interests: return ok([])
    preferred = [x["category"] for x in interests]
    related = list(CategoryRelation.objects.filter(category__name__in=preferred)
                   .values_list("neighbor__name", flat=True))
    categories = preferred + [x for x in related if x not in preferred]
    qs = Project.objects.filter(status="PUBLIE", category__in=categories).select_related("developer").defer("icon_data")
    seen_ids = list(VisitorActivity.objects.filter(visitor=visitor, activity_type="project_open", project__isnull=False)
                    .values_list("project_id", flat=True).distinct())
    qs = qs.exclude(id__in=seen_ids).order_by("-featured", "-created_at")
    items = list(qs[:8])
    return ok([project_list_public(p) for p in items])

@admin_only
def admin_developers(request):
    qs=DeveloperProfile.objects.select_related("user").filter(email_verified=True, user__is_staff=False)
    s=request.GET.get("search","").strip()
    if s: qs=qs.filter(Q(user__username__icontains=s)|Q(user__email__icontains=s)|Q(user__first_name__icontains=s))
    return ok([{"id":p.user.id,"display_name":p.user.get_full_name() or p.user.username,"username":p.public_username or p.user.username,"email":p.user.email,"created_at":p.user.date_joined.isoformat(),"status":p.status} for p in qs.order_by("-user__date_joined")])

@admin_only
def admin_reports(request):
    if request.method == "POST":
        data = json_body(request)
        kind = str(data.get("kind", ""))
        report_id = data.get("id")
        model = CommentReport if kind == "comment" else Report if kind == "project" else None
        if model is None:
            return err("Type de signalement invalide.")
        report = model.objects.filter(pk=report_id).first()
        if not report:
            return err("Signalement introuvable.", 404)
        report.status = "TRAITE"
        report.save(update_fields=["status"])
        return ok({"message": "Signalement marqué comme traité."})
    if request.method != "GET":
        return err("Méthode non autorisée.", 405)
    items = []
    for r in Report.objects.select_related("project", "project__developer").order_by("-created_at"):
        items.append({"id": r.id, "kind": "project", "project_name": r.project.name,
                      "developer_name": r.project.developer.get_full_name() or r.project.developer.username,
                      "author_name": "", "reason": r.reason, "description": r.description,
                      "status": r.status, "created_at": r.created_at.isoformat()})
    for r in CommentReport.objects.select_related("comment", "comment__project", "comment__project__developer").order_by("-created_at"):
        items.append({"id": r.id, "kind": "comment", "project_name": r.comment.project.name,
                      "developer_name": r.comment.project.developer.get_full_name() or r.comment.project.developer.username,
                      "author_name": r.comment.author_name, "reason": r.reason, "description": r.description,
                      "status": r.status, "created_at": r.created_at.isoformat()})
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return ok(items)


@admin_only
def admin_suspended_developers(request):
    qs = DeveloperProfile.objects.select_related("user").filter(status="SUSPENDU", email_verified=True, user__is_staff=False).order_by("-user__date_joined")
    return ok([{"id":p.user_id,"display_name":p.user.get_full_name() or p.user.username,"username":p.public_username or p.user.username,
                "email":p.user.email,"created_at":p.user.date_joined.isoformat(),"suspension_reason":p.suspension_reason,
                "appeal_message":p.appeal_message,"appeal_status":p.appeal_status,
                "appealed_at":p.appealed_at.isoformat() if p.appealed_at else None} for p in qs])


@admin_only
def admin_developer_detail(request,user_id):
    if request.method=="DELETE":
        p=DeveloperProfile.objects.select_related("user").filter(user_id=user_id, user__is_staff=False).first()
        if not p: return err("Développeur introuvable.",404)
        p.user.delete()
        return ok(None,204)
    p=DeveloperProfile.objects.select_related("user").filter(user_id=user_id, user__is_staff=False).first()
    if not p:return err("Développeur introuvable.",404)
    u=p.user; projects=Project.objects.filter(developer=u)
    return ok({"id":u.id,"display_name":u.get_full_name() or u.username,"username":p.public_username or u.username,"email":u.email,"created_at":u.date_joined.isoformat(),"status":p.status,
               "suspension_reason":p.suspension_reason,"appeal_message":p.appeal_message,"appeal_status":p.appeal_status,
               "appealed_at":p.appealed_at.isoformat() if p.appealed_at else None,
               "projects":[{"id":x.id,"name":x.name,"status":x.status} for x in projects],
               "stats":{"total_views":Event.objects.filter(project__developer=u,type="view").count(),"total_visit_clicks":Event.objects.filter(project__developer=u,type="visit_click").count(),"total_installs":Event.objects.filter(project__developer=u,type="install").count()},
               "reports":[{"project_name":r.project.name,"reason":r.reason} for r in Report.objects.filter(project__developer=u).order_by("-created_at")]})

@admin_only
def admin_developer_suspend(request,user_id):
    if request.method!="POST":return err("Méthode non autorisée.",405)
    p=DeveloperProfile.objects.filter(user_id=user_id, user__is_staff=False).first()
    if not p:return err("Développeur introuvable.",404)
    reason = str(json_body(request).get("reason", "")).strip()
    if len(reason) < 5:return err("Le motif de suspension doit contenir au moins 5 caractères.")
    if len(reason) > 5000:return err("Le motif est trop long.")
    p.status="SUSPENDU";p.suspension_reason=reason;p.appeal_message="";p.appeal_status="AUCUNE";p.appealed_at=None
    p.user.is_active=False;p.user.save(update_fields=["is_active"])
    AuthToken.objects.filter(user=p.user, kind="dev").delete()
    p.save(update_fields=["status","suspension_reason","appeal_message","appeal_status","appealed_at"])
    return ok({"message":"Compte suspendu."})

@admin_only
def admin_developer_reactivate(request,user_id):
    if request.method!="POST":return err("Méthode non autorisée.",405)
    p=DeveloperProfile.objects.filter(user_id=user_id, user__is_staff=False).first()
    if not p:return err("Développeur introuvable.",404)
    p.status="ACTIF";p.suspension_reason="";p.appeal_status="AUCUNE";p.appeal_message="";p.appealed_at=None
    p.user.is_active=True;p.user.save(update_fields=["is_active"]);p.save(update_fields=["status","suspension_reason","appeal_status","appeal_message","appealed_at"])
    return ok({"message":"Compte réactivé."})

def _send_web_push(subscription, notification):
    """Envoie une notification push si les clés VAPID sont configurées."""
    private_key = getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "")
    subject = getattr(settings, "WEBPUSH_VAPID_SUBJECT", "mailto:dekalhouse@gmail.com")
    if not private_key:
        return False
    try:
        from pywebpush import webpush, WebPushException
        payload = json.dumps({
            "title": notification.title,
            "body": notification.body,
            "url": notification.target_url or "/",
            "notification_id": notification.id,
        })
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=payload,
            vapid_private_key=private_key,
            vapid_claims={"sub": subject},
            ttl=60 * 60 * 24,
        )
        return True
    except Exception as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code in (404, 410):
            subscription.delete()
        return False


def _create_notification(recipient, title, body="", category="system", target_url="", send_push=True):
    notification = Notification.objects.create(
        recipient=recipient,
        title=str(title)[:180],
        body=str(body)[:1000],
        category=category if category in {"message", "project", "activity", "system", "security"} else "system",
        target_url=str(target_url)[:500],
    )
    if send_push and getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", ""):
        for subscription in PushSubscription.objects.filter(user=recipient).iterator():
            _send_web_push(subscription, notification)
    return notification


@csrf_exempt
@require("dev")
def dev_notifications(request):
    if request.method == "GET":
        rows = Notification.objects.filter(recipient=request.api_user)[:200]
        return ok([{
            "id": n.id, "title": n.title, "body": n.body,
            "category": n.category, "target_url": n.target_url,
            "is_read": n.is_read, "created_at": n.created_at.isoformat(),
        } for n in rows])
    if request.method == "PATCH":
        b = json_body(request)
        if b.get("mark_all_read") is True:
            Notification.objects.filter(recipient=request.api_user, is_read=False).update(is_read=True)
            return ok({"message": "Notifications marquées comme lues."})
        try:
            notification_id = int(b.get("id"))
        except (TypeError, ValueError):
            return err("Notification invalide.")
        updated = Notification.objects.filter(
            id=notification_id, recipient=request.api_user, is_read=False
        ).update(is_read=True)
        if not updated and not Notification.objects.filter(id=notification_id, recipient=request.api_user).exists():
            return err("Notification introuvable.", 404)
        return ok({"message": "Notification marquée comme lue."})
    return err("Méthode non autorisée.", 405)


@csrf_exempt
@require("dev")
def dev_push_public_key(request):
    if request.method != "GET":
        return err("Méthode non autorisée.", 405)
    return ok({
        "public_key": getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", ""),
        "configured": bool(getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "") and getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "")),
    })


@csrf_exempt
@require("dev")
def dev_push_subscriptions(request):
    if request.method == "POST":
        b = json_body(request)
        endpoint = str(b.get("endpoint", "")).strip()
        keys = b.get("keys") or {}
        p256dh, auth = str(keys.get("p256dh", "")), str(keys.get("auth", ""))
        parsed_endpoint = urlsplit(endpoint)
        host = (parsed_endpoint.hostname or "").lower().rstrip(".")
        trusted_push_hosts = (
            host == "fcm.googleapis.com"
            or host.endswith(".mozilla.com")
            or host.endswith(".mozilla.org")
            or host.endswith(".windows.com")
            or host.endswith(".apple.com")
        )
        if (
            parsed_endpoint.scheme != "https" or not trusted_push_hosts
            or not p256dh or not auth or len(endpoint) > 2000
        ):
            return err("Abonnement push invalide.")

        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "user": request.api_user,
                "p256dh": p256dh[:255],
                "auth": auth[:255],
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
            },
        )
        return ok({"message": "Cet appareil est abonné aux notifications."}, 201)
    if request.method == "DELETE":
        endpoint = str(json_body(request).get("endpoint", "")).strip()
        if endpoint:
            PushSubscription.objects.filter(user=request.api_user, endpoint=endpoint).delete()
        return ok({"message": "Abonnement supprimé."})
    return err("Méthode non autorisée.", 405)


def _email_admin_message(recipient, subject, content, sender):
    """Envoie par e-mail une copie d'un message de l'administration."""
    if not recipient.email:
        return False
    sender_name = sender.get_full_name() or sender.username or "Administration WEB STORE"
    safe_subject = html_escape(subject)
    safe_sender = html_escape(sender_name)
    safe_content = html_escape(content).replace("\n", "<br>")
    text_content = (
        f"Bonjour {recipient.get_full_name() or recipient.username},\n\n"
        f"Vous avez reçu un nouveau message de {sender_name} sur WEB STORE.\n\n"
        f"Sujet : {subject}\n\n{content}\n\n"
        "Connectez-vous à votre espace développeur WEB STORE pour consulter vos messages."
    )
    html_content = f"""<!doctype html>
<html lang="fr"><body style="margin:0;padding:24px;background:#f3f4f6;font-family:Arial,sans-serif;color:#172033;">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
    <div style="padding:20px 24px;background:#16A34A;color:#ffffff;font-size:20px;font-weight:bold;">WEB STORE</div>
    <div style="padding:24px;">
      <p>Bonjour {html_escape(recipient.get_full_name() or recipient.username)},</p>
      <p>Vous avez reçu un nouveau message de <strong>{safe_sender}</strong>.</p>
      <h2 style="font-size:18px;margin:22px 0 12px;">{safe_subject}</h2>
      <div style="padding:16px;background:#f9fafb;border-left:4px solid #16A34A;border-radius:6px;line-height:1.6;">{safe_content}</div>
      <p style="margin-top:22px;">Connectez-vous à votre espace développeur WEB STORE pour consulter vos messages et répondre.</p>
      <p style="color:#6b7280;font-size:12px;margin-top:28px;">https://web-store-dev.onrender.com</p>
    </div>
  </div>
</body></html>"""
    return send_transactional_email(recipient.email, subject, text_content, html_content)


@admin_only
def admin_developer_message(request,user_id):
    if request.method!="POST":return err("Méthode non autorisée.",405)
    recipient=User.objects.filter(id=user_id).first()
    if not recipient:return err("Développeur introuvable.",404)
    b=json_body(request); subject=str(b.get("subject","")).strip();content=str(b.get("content","")).strip()
    if not subject or not content:return err("Sujet et contenu requis.")
    m=Message.objects.create(sender=request.api_user,recipient=recipient,subject=subject,content=content)
    email_sent = _email_admin_message(recipient, subject, content, request.api_user)
    notification = _create_notification(
        recipient,
        subject or "Nouveau message de l'administration",
        content[:240],
        category="message",
        target_url=f"/pages/messages.html?id={m.id}",
    )
    return ok({"id":m.id, "email_sent":email_sent, "notification_id":notification.id},201)

@admin_only
def admin_message_all_developers(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    b = json_body(request)
    subject = str(b.get("subject", "")).strip()
    content = str(b.get("content", "")).strip()
    if not subject or not content:
        return err("Sujet et contenu requis.")
    recipients = User.objects.filter(developer_profile__isnull=False, is_active=True)
    if not recipients.exists():
        return err("Aucun développeur actif à contacter.", 404)
    recipient_list = list(recipients)
    messages = [
        Message(sender=request.api_user, recipient=recipient, subject=subject, content=content)
        for recipient in recipient_list
    ]
    Message.objects.bulk_create(messages)
    notification_count = 0
    for recipient, message in zip(recipient_list, messages):
        _create_notification(
            recipient, subject or "Nouveau message de l'administration",
            content[:240], category="message",
            target_url=f"/pages/messages.html?id={message.id}",
        )
        notification_count += 1
    email_sent_count = sum(
        1 for recipient in recipient_list
        if _email_admin_message(recipient, subject, content, request.api_user)
    )
    return ok({
        "message": "Message envoyé à tous les développeurs actifs.",
        "sent_count": len(messages),
        "email_sent_count": email_sent_count,
        "notification_count": notification_count,
    }, 201)

@admin_only
def admin_publications(request):
    qs=Project.objects.select_related("developer").all()
    s=request.GET.get("search","").strip(); status=request.GET.get("status","").strip()
    if s: qs=qs.filter(Q(name__icontains=s)|Q(developer__username__icontains=s)|Q(developer__first_name__icontains=s))
    if status: qs=qs.filter(status=status)
    return ok([project_admin(p) for p in qs.order_by("-created_at")])

def project_admin(p):
    d={**project_public(p),"developer_name":p.developer.get_full_name() or p.developer.username}
    d["stats"]={"comments":p.comments.count(),
                 "visits":Event.objects.filter(project=p,type="view").count(),
                 "downloads":Event.objects.filter(project=p,type="install").count() if p.type=="PWA" else None}
    return d

@admin_only
def admin_publication_detail(request,project_id):
    if request.method=="DELETE":
        p=Project.objects.filter(id=project_id).first()
        if not p: return err("Publication introuvable.",404)
        b=json_body(request); reason=str(b.get("reason","")).strip()
        if not reason: return err("Motif requis.")
        ModerationLog.objects.create(admin=request.api_user,project=p,action="SUPPRIME",reason=reason)
        p.delete(); return ok(None,204)
    p=Project.objects.select_related("developer").filter(id=project_id).first()
    if not p:return err("Publication introuvable.",404)
    d=project_admin(p);d["rejection_reason"]=p.rejection_reason;d["suspension_reason"]=p.suspension_reason
    d["comments"]=[{"id":c.id,"author_name":c.author_name,"content":c.content,"is_hidden":c.is_hidden,"created_at":c.created_at.isoformat()} for c in p.comments.order_by("-created_at")]
    d["comment_reports"]=[{"comment_id":r.comment_id,"comment_author":r.comment.author_name,"reason":r.reason,"description":r.description,"created_at":r.created_at.isoformat(),"status":r.status} for r in CommentReport.objects.filter(comment__project=p).select_related("comment").order_by("-created_at")]
    d["reports"]=[{"reason":r.reason,"description":r.description} for r in p.reports.order_by("-created_at")]
    return ok(d)

@admin_only
def admin_publication_feature(request,project_id):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    p=Project.objects.filter(id=project_id).first()
    if not p: return err("Publication introuvable.",404)
    featured=bool(json_body(request).get("featured", not p.featured))
    p.featured=featured
    p.save(update_fields=["featured","updated_at"])
    ModerationLog.objects.create(admin=request.api_user,project=p,action="MISE_A_LA_UNE" if featured else "RETRAIT_A_LA_UNE")
    return ok(project_admin(p))

def moderation(project,admin,action,reason=""):
    project.status=action
    if action=="REJETE":
        project.rejection_reason=reason
        project.featured=False
    if action=="SUSPENDU":
        project.suspension_reason=reason
        project.featured=False
    if action=="PUBLIE": project.rejection_reason="";project.suspension_reason=""
    project.save()
    ModerationLog.objects.create(admin=admin,project=project,action=action,reason=reason)

@admin_only
def admin_publication_approve(request,project_id):
    if request.method!="POST":return err("Méthode non autorisée.",405)
    p=Project.objects.filter(id=project_id).first()
    if not p:return err("Publication introuvable.",404)
    moderation(p,request.api_user,"PUBLIE");return ok(project_admin(p))

@admin_only
def admin_publication_reject(request,project_id):
    if request.method!="POST":return err("Méthode non autorisée.",405)
    p=Project.objects.filter(id=project_id).first()
    if not p:return err("Publication introuvable.",404)
    reason=str(json_body(request).get("reason","")).strip()
    if not reason:return err("Motif requis.")
    moderation(p,request.api_user,"REJETE",reason);return ok(project_admin(p))

@admin_only
def admin_publication_suspend(request,project_id):
    if request.method!="POST":return err("Méthode non autorisée.",405)
    p=Project.objects.filter(id=project_id).first()
    if not p:return err("Publication introuvable.",404)
    reason=str(json_body(request).get("reason","")).strip()
    if not reason:return err("Motif requis.")
    moderation(p,request.api_user,"SUSPENDU",reason);return ok(project_admin(p))



# Messagerie de l'administration : boîte de réception, messages envoyés et réponses.
@admin_only
def admin_messages(request):
    if request.method != "GET":
        return err("Méthode non autorisée.", 405)
    box = request.GET.get("box", "inbox")
    qs = Message.objects.select_related("sender", "recipient")
    if box == "sent":
        qs = qs.filter(sender=request.api_user)
    else:
        qs = qs.filter(recipient=request.api_user)
    rows = []
    for m in qs.order_by("-created_at")[:300]:
        other = m.sender if box == "inbox" else m.recipient
        rows.append({
            "id": m.id, "subject": m.subject, "content": m.content,
            "read": m.read, "created_at": m.created_at.isoformat(),
            "sender_name": m.sender.get_full_name() or m.sender.username,
            "sender_email": m.sender.email,
            "recipient_name": m.recipient.get_full_name() or m.recipient.username,
            "recipient_email": m.recipient.email,
            "other_name": other.get_full_name() or other.username,
            "other_email": other.email,
            "is_reply": bool(m.parent_id),
        })
    return ok(rows)

@admin_only
def admin_message_detail(request, message_id):
    m = Message.objects.select_related("sender", "recipient").filter(
        id=message_id, recipient=request.api_user
    ).first()
    if not m:
        # L'administration peut également ouvrir un message qu'elle a envoyé.
        m = Message.objects.select_related("sender", "recipient").filter(
            id=message_id, sender=request.api_user
        ).first()
    if not m:
        return err("Message introuvable.", 404)
    if request.method == "PATCH":
        if m.recipient_id == request.api_user.id and json_body(request).get("read") is True and not m.read:
            m.read = True
            m.save(update_fields=["read"])
        return ok({"message": "Message mis à jour.", "read": m.read})
    if request.method == "DELETE":
        m.delete()
        return ok({"message": "Message supprimé."})
    if request.method != "GET":
        return err("Méthode non autorisée.", 405)
    return ok({
        "id": m.id, "subject": m.subject, "content": m.content,
        "read": m.read, "created_at": m.created_at.isoformat(),
        "sender_name": m.sender.get_full_name() or m.sender.username,
        "sender_email": m.sender.email,
        "recipient_name": m.recipient.get_full_name() or m.recipient.username,
        "recipient_email": m.recipient.email,
    })

@admin_only
def admin_message_reply(request, message_id):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    original = Message.objects.filter(id=message_id, recipient=request.api_user).first()
    if not original:
        return err("Seuls les messages reçus peuvent recevoir une réponse ici.", 404)
    content = str(json_body(request).get("content", "")).strip()
    if not content:
        return err("Le contenu du message est requis.")
    if len(content) > 10000:
        return err("Le message ne doit pas dépasser 10 000 caractères.")
    reply_subject = (original.subject if original.subject.lower().startswith("re:") else "Re: " + original.subject)[:200]
    reply = Message.objects.create(
        sender=request.api_user, recipient=original.sender,
        subject=reply_subject, content=content, parent=original,
    )
    email_sent = _email_admin_message(original.sender, reply_subject, content, request.api_user)
    return ok({"id": reply.id, "message": "Réponse envoyée.", "email_sent": email_sent}, 201)


# ---------------------------------------------------------------------------
# Campagnes sponsorisées — API phase 2
# ---------------------------------------------------------------------------
def _validate_campaign_image(value):
    if not value:
        return ""
    if not isinstance(value, str) or len(value) > 2_000_000:
        raise ValueError("Image invalide ou trop volumineuse. Réduisez sa taille et réessayez.")
    header, separator, encoded = value.partition(",")
    if not separator or not re.fullmatch(r"data:image/(png|jpeg|webp|gif);base64", header, re.IGNORECASE):
        raise ValueError("Fichier image invalide.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError("Fichier image invalide.")
    if not raw or len(raw) > 1_500_000:
        raise ValueError("Image invalide ou trop volumineuse. Réduisez sa taille et réessayez.")
    mime = "image/" + header[11:header.index(";")].lower()
    signatures = {
        "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
        "image/gif": raw.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP",
    }
    if not signatures.get(mime, False):
        raise ValueError("Le contenu du fichier ne correspond pas à une image valide.")
    return value


def _campaign_payload(campaign):
    p = campaign.project
    counts = campaign.events.aggregate(
        impressions=Count("id", filter=Q(event_type="impression")),
        clicks=Count("id", filter=Q(event_type="click")),
    )
    return {
        "id": campaign.id, "project_id": p.id, "project_name": p.name,
        "developer_id": p.developer_id,
        "developer": p.developer.get_full_name() or p.developer.username,
        "title": campaign.title, "target_categories": campaign.target_categories,
        "status": campaign.status, "payment_status": campaign.payment_status,
        "starts_at": campaign.starts_at.isoformat() if campaign.starts_at else None,
        "ends_at": campaign.ends_at.isoformat() if campaign.ends_at else None,
        "image_url": campaign.image_url, "image_data": campaign.image_data, "admin_note": campaign.admin_note,
        "created_at": campaign.created_at.isoformat(),
        "impressions": counts["impressions"] or 0, "clicks": counts["clicks"] or 0,
    }

@csrf_exempt
@require("dev")
def dev_sponsored_campaigns(request):
    if request.method == "GET":
        qs = SponsoredCampaign.objects.filter(project__developer=request.api_user).select_related("project", "project__developer")
        return ok([_campaign_payload(c) for c in qs])
    if request.method != "POST": return err("Méthode non autorisée.", 405)
    b = json_body(request)
    try: project_id = int(b.get("project_id"))
    except (TypeError, ValueError): return err("Projet invalide.")
    project = Project.objects.filter(id=project_id, developer=request.api_user, status="PUBLIE").first()
    if not project: return err("Projet publié introuvable ou non autorisé.", 404)
    title = str(b.get("title") or project.name).strip()[:160]
    if not title: return err("Le titre de la campagne est requis.")
    categories = b.get("target_categories", [])
    if not isinstance(categories, list) or any(not isinstance(x, str) for x in categories):
        return err("Les catégories ciblées doivent être une liste de textes.")
    categories = list(dict.fromkeys(x.strip()[:100] for x in categories if x.strip()))[:30]
    campaign = SponsoredCampaign.objects.create(
        project=project, title=title, target_categories=categories,
        status="EN_ATTENTE", payment_status="NON_PAYE",
    )
    return ok(_campaign_payload(campaign), 201)

@csrf_exempt
@admin_only
def admin_sponsored_campaigns(request):
    if request.method == "GET":
        qs = SponsoredCampaign.objects.select_related("project", "project__developer").all()
        status = request.GET.get("status", "").strip()
        if status: qs = qs.filter(status=status)
        return ok([_campaign_payload(c) for c in qs])
    if request.method != "POST": return err("Méthode non autorisée.", 405)
    b = json_body(request)
    try: project_id = int(b.get("project_id"))
    except (TypeError, ValueError): return err("Projet invalide.")
    project = Project.objects.filter(id=project_id, status="PUBLIE").first()
    if not project: return err("Projet publié introuvable.", 404)
    title = str(b.get("title") or project.name).strip()[:160]
    cats = b.get("target_categories", [])
    if not isinstance(cats, list) or any(not isinstance(x, str) for x in cats): return err("Catégories invalides.")
    try: image_data = _validate_campaign_image(b.get("image_data", ""))
    except ValueError as exc: return err(str(exc))
    campaign = SponsoredCampaign.objects.create(project=project, title=title or project.name,
        target_categories=list(dict.fromkeys(x.strip()[:100] for x in cats if x.strip()))[:30],
        image_data=image_data, status="BROUILLON", payment_status="NON_PAYE")
    return ok(_campaign_payload(campaign), 201)

@csrf_exempt
@admin_only
def admin_sponsored_campaign_detail(request, campaign_id):
    campaign = SponsoredCampaign.objects.select_related("project", "project__developer").filter(id=campaign_id).first()
    if not campaign: return err("Campagne introuvable.", 404)
    if request.method == "GET": return ok(_campaign_payload(campaign))
    # DELETE doit être traité avant le contrôle PATCH.
    if request.method == "DELETE":
        campaign.delete()
        return ok({"deleted": True, "id": campaign_id})
    if request.method != "PATCH": return err("Méthode non autorisée.", 405)
    b = json_body(request)
    allowed_status = {x[0] for x in SponsoredCampaign.STATUS_CHOICES}
    allowed_payment = {x[0] for x in SponsoredCampaign.PAYMENT_CHOICES}

    # Appliquer d'abord le paiement, puis vérifier le statut demandé.
    # Ainsi PAYE + ACTIVE envoyés dans la même requête sont correctement acceptés.
    if "payment_status" in b:
        payment_value = str(b["payment_status"])
        if payment_value not in allowed_payment: return err("Statut de paiement invalide.")
        campaign.payment_status = payment_value

    if "status" in b:
        status_value = str(b["status"])
        if status_value not in allowed_status: return err("Statut de campagne invalide.")
        if status_value == "ACTIVE" and campaign.payment_status != "PAYE":
            return err("Confirmez d'abord le paiement avant d'activer la campagne.", 409)
        campaign.status = status_value
        if status_value == "ACTIVE" and not campaign.approved_at:
            campaign.approved_at = timezone.now()
    elif "payment_status" in b and campaign.payment_status != "PAYE" and campaign.status == "ACTIVE":
        # Un paiement retiré/refusé ne peut pas laisser une campagne active.
        campaign.status = "SUSPENDUE"
    if "starts_at" in b:
        raw = b["starts_at"]
        try: campaign.starts_at = timezone.datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
        except Exception: return err("Date de début invalide.")
    if "ends_at" in b:
        raw = b["ends_at"]
        try: campaign.ends_at = timezone.datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
        except Exception: return err("Date d'expiration invalide.")
    if campaign.starts_at and campaign.ends_at and campaign.ends_at <= campaign.starts_at:
        return err("La date d'expiration doit être postérieure au début.")
    if "title" in b:
        title = str(b.get("title") or "").strip()[:160]
        if not title: return err("Le titre de la campagne est requis.")
        campaign.title = title
    if "project_id" in b:
        try: project_id = int(b["project_id"])
        except (TypeError, ValueError): return err("Projet invalide.")
        project = Project.objects.filter(id=project_id, status="PUBLIE").first()
        if not project: return err("Projet publié introuvable.", 404)
        campaign.project = project
    if "image_url" in b: campaign.image_url = str(b["image_url"] or "").strip()[:1000]
    if "image_data" in b:
        try: campaign.image_data = _validate_campaign_image(b.get("image_data", ""))
        except ValueError as exc: return err(str(exc))
    if "admin_note" in b: campaign.admin_note = str(b["admin_note"] or "")[:5000]
    if "target_categories" in b:
        cats = b["target_categories"]
        if not isinstance(cats, list) or any(not isinstance(x, str) for x in cats): return err("Catégories invalides.")
        campaign.target_categories = list(dict.fromkeys(x.strip()[:100] for x in cats if x.strip()))[:30]
    campaign.save()
    return ok(_campaign_payload(campaign))


@csrf_exempt
def public_sponsored_campaign(request):
    """Retourne toutes les campagnes actives correspondant aux centres d'intérêt."""
    if request.method != "GET":
        return err("Méthode non autorisée.", 405)
    visitor = _visitor_from_request(request)
    if not visitor:
        return ok([])

    interests = VisitorActivity.objects.filter(visitor=visitor).exclude(category="").values(
        "category"
    ).annotate(score=Count("id")).order_by("-score")[:20]
    preferred = {str(item["category"]).strip().casefold() for item in interests if item["category"]}
    if not preferred:
        return ok([])

    now = timezone.now()
    campaigns = SponsoredCampaign.objects.select_related(
        "project", "project__developer"
    ).filter(
        status="ACTIVE", payment_status="PAYE", project__status="PUBLIE"
    ).filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now)).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now)
    )
    eligible = []
    for campaign in campaigns:
        targets = campaign.target_categories or []
        if not targets or preferred.intersection(str(x).strip().casefold() for x in targets):
            eligible.append(campaign)

    # Expiration la plus proche d'abord ; campagnes sans date de fin ensuite ;
    # à expiration égale, la campagne créée le plus récemment est prioritaire.
    eligible.sort(key=lambda c: (c.ends_at is None, c.ends_at or timezone.datetime.max.replace(tzinfo=timezone.get_current_timezone()), -c.created_at.timestamp()))
    return ok([{
        "id": campaign.id,
        "title": campaign.title,
        "image_url": campaign.image_url,
        "image_data": campaign.image_data,
        "ends_at": campaign.ends_at.isoformat() if campaign.ends_at else None,
        "project": project_list_public(campaign.project),
    } for campaign in eligible])


@csrf_exempt
def public_sponsored_campaign_event(request, campaign_id):
    """Enregistre une impression ou un clic publicitaire pour un visiteur connu."""
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    visitor = _visitor_from_request(request)
    if not visitor:
        return err("Identité visiteur invalide. Rechargez la page.", 401)
    if _rate_limited(request, "sponsored_event_ip", 500, 3600, identity=str(campaign_id)):
        return err("Trop d'événements publicitaires depuis cette connexion.", 429)
    if _rate_limited(request, "sponsored_event", 60, 3600, identity=f"{campaign_id}:{_visitor_rate_identity(request)}"):
        return err("Trop d'événements publicitaires. Réessayez plus tard.", 429)
    campaign = SponsoredCampaign.objects.filter(
        id=campaign_id, status="ACTIVE", payment_status="PAYE", project__status="PUBLIE"
    ).first()
    if not campaign:
        return err("Campagne indisponible.", 404)
    now = timezone.now()
    if campaign.starts_at and campaign.starts_at > now:
        return err("Campagne pas encore commencée.", 404)
    if campaign.ends_at and campaign.ends_at <= now:
        return err("Campagne expirée.", 404)
    body = json_body(request)
    event_type = str(body.get("type", "")).strip()
    if event_type not in {"impression", "click"}:
        return err("Type d'événement invalide.")
    dedupe_seconds = 1800 if event_type == "impression" else 60
    recent = SponsoredCampaignEvent.objects.filter(
        campaign=campaign, visitor=visitor, event_type=event_type,
        created_at__gte=timezone.now() - timedelta(seconds=dedupe_seconds),
    ).exists()
    if recent:
        return ok({"recorded": False, "message": "Événement déjà comptabilisé récemment."})
    SponsoredCampaignEvent.objects.create(
        campaign=campaign, visitor=visitor, event_type=event_type
    )
    return ok({"recorded": True}, 201)
