import hashlib, secrets, base64, re, json, hmac
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
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.text import slugify
from .models import DeveloperProfile, Category, Project, Comment, Report, Event, AuthToken, Message, ModerationLog, Visitor, EmailCode, Favorite

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
def issue_token(user, kind):
    raw = secrets.token_urlsafe(32)
    AuthToken.objects.create(key_hash=hash_token(raw), user=user, kind=kind)
    return raw

def auth_user(request, kind=None):
    value=request.headers.get("Authorization","")
    if not value.startswith("Bearer "): return None
    raw=value[7:].strip()
    if not raw: return None
    token=AuthToken.objects.select_related("user").filter(key_hash=hash_token(raw)).first()
    if not token: return None
    if kind and token.kind != kind: return None
    if not token.user.is_active: return None
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
    d["comments"] = [{"id": c.id, "author_name": c.author_name, "content": c.content, "created_at": c.created_at.isoformat()} for c in p.comments.order_by("-created_at")]
    event_counts = p.events.values("type").annotate(total=Count("id"))
    counts = {item["type"]: item["total"] for item in event_counts}
    d["visits_count"] = counts.get("visit_click", 0)
    d["views_count"] = counts.get("view", 0)
    d["installs_count"] = counts.get("install", 0)
    return d

@csrf_exempt
def visitor_track(request):
    if request.method != "POST": return err("Méthode non autorisée.",405)
    raw = request.headers.get("X-Visitor-ID", "").strip()
    if not raw:
        raw = secrets.token_urlsafe(32)
    visitor, created = Visitor.objects.get_or_create(visitor_id=raw)
    if not created:
        visitor.save(update_fields=["last_seen"])
    return ok({"visitor_id": raw, "new_visitor": created})

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
    return ok([project_list_public(p) for p in qs.order_by("-featured", "-created_at")])

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
    visitor_id = request.headers.get("X-Visitor-ID", "").strip()
    if not visitor_id or len(visitor_id) > 64:
        return err("Identifiant visiteur manquant. Rechargez la page.", 400)
    visitor = Visitor.objects.filter(visitor_id=visitor_id).first()
    if not visitor:
        return err("Visiteur inconnu. Rechargez la page.", 400)
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
    project = Project.objects.filter(
        slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]
    ).first()
    if not project:
        return err("Projet introuvable.", 404)

    if request.method == "GET":
        comments = project.comments.order_by("-created_at")
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

        # Le jeton brut n'est retourné qu'une fois à l'auteur ; la base ne
        # conserve que son empreinte SHA-256.
        manage_token = secrets.token_urlsafe(32)
        comment = Comment.objects.create(
            project=project,
            author_name=name,
            content=content,
            manage_token_hash=hash_token(manage_token),
        )
        return ok({
            "id": comment.id,
            "author_name": comment.author_name,
            "content": comment.content,
            "created_at": comment.created_at.isoformat(),
            "manage_token": manage_token,
        }, 201)

    return err("Méthode non autorisée.", 405)


@csrf_exempt
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
    b=json_body(request); reason=str(b.get("reason","")).strip(); description=str(b.get("description","")).strip()
    if not reason: return err("Motif requis.")
    r=Report.objects.create(project=p,reason=reason[:200],description=description[:5000])
    return ok({"id":r.id,"message":"Signalement enregistré."},201)

@csrf_exempt
def project_event(request,slug):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    p=Project.objects.filter(slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]).first()
    if not p: return err("Projet introuvable.",404)
    typ=json_body(request).get("type")
    if typ not in {"view","visit_click","install"}: return err("Type d'événement invalide.")
    Event.objects.create(project=p,type=typ)
    return ok({"message":"Événement enregistré."},201)


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


@csrf_exempt
def dev_register(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    b = json_body(request)
    full = str(b.get("full_name", "")).strip()
    username = str(b.get("username", "")).strip()
    email = str(b.get("email", "")).strip().lower()
    phone = str(b.get("phone", "")).strip()
    password = b.get("password", "")

    if not all([full, username, email, password]):
        return err("Nom, username, e-mail et mot de passe requis.")
    if not isinstance(password, str):
        return err("Mot de passe invalide.")
    try:
        validate_email(email)
    except ValidationError:
        return err("Adresse e-mail invalide.", 400)
    if User.objects.filter(Q(username__iexact=username) | Q(email__iexact=email)).exists():
        return err("Ce compte existe déjà.", 409)

    # La vérification d'e-mail est obligatoire : ne jamais créer un profil
    # considéré comme vérifié par défaut.
    if not (settings.BREVO_API_KEY or (
        settings.EMAIL_PROVIDER == "smtp" and getattr(settings, "EMAIL_HOST", "")
    )):
        return err("Le service d'e-mail n'est pas configuré. Contactez l'administration.", 503)

    try:
        user_candidate = User(username=username, email=email, first_name=full)
        validate_password(password, user=user_candidate)
        with transaction.atomic():
            user = User.objects.create_user(
                username=username, email=email, password=password, first_name=full
            )
            DeveloperProfile.objects.create(
                user=user,
                phone=phone,
                email_verified=False,
            )
    except ValidationError as exc:
        return err(" ".join(exc.messages), 400)
    except Exception:
        return err("Impossible de créer le compte.", 500)

    sent, result = _issue_email_code(user, "verification")
    if not sent:
        user.delete()
        if result == "cooldown":
            return err("Veuillez patienter avant de demander un nouveau code.", 429)
        return err("L'envoi de l'e-mail a échoué. Réessayez plus tard.", 503)

    return ok({
        "message": "Compte créé. Vérifiez votre adresse e-mail avec le code envoyé.",
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

    user = User.objects.filter(email__iexact=email).first()
    if not user or not hasattr(user, "developer_profile"):
        return err("Code invalide.", 400)
    profile = user.developer_profile
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

    # La vérification termine l'inscription et ouvre directement la session dev.
    if profile.status != "ACTIF":
        return err("Votre compte n'est pas actif.", 403)

    return ok({
        "message": "E-mail vérifié.",
        "token": issue_token(user, "dev"),
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.get_full_name(),
        },
    })


@csrf_exempt
def dev_resend_code(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    email = str(json_body(request).get("email", "")).strip().lower()
    user = User.objects.filter(email__iexact=email).first()
    if user and hasattr(user, "developer_profile") and not user.developer_profile.email_verified:
        sent, result = _issue_email_code(user, "verification")
        if not sent and result == "send_failed":
            return err("Impossible d'envoyer le code pour le moment.", 503)
        if not sent and result == "cooldown":
            return err("Veuillez patienter avant de demander un nouveau code.", 429)
    return ok({"message": "Si le compte existe et nécessite une vérification, un code a été envoyé."})


@csrf_exempt
def dev_login(request):
    if request.method != "POST":
        return err("Méthode non autorisée.", 405)
    b = json_body(request)
    email = str(b.get("email", "")).strip()
    username = User.objects.filter(email__iexact=email).values_list("username", flat=True).first() or ""
    user = authenticate(username=username, password=b.get("password", ""))
    if not user or not hasattr(user, "developer_profile"):
        return err("Identifiants invalides.", 401)
    profile = user.developer_profile
    if profile.status != "ACTIF":
        return err("Compte non actif.", 401)
    if not profile.email_verified:
        return err("E-mail non vérifié. Consultez votre boîte de réception et validez votre adresse.", 401)
    return ok({
        "token": issue_token(user, "dev"),
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.get_full_name(),
        },
    })


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
    return ok({"message": "Mot de passe mis à jour."})

@require("dev")
def dev_me(request):
    u=request.api_user; p=u.developer_profile
    return ok({"id":u.id,"full_name":u.get_full_name(),"username":u.username,"email":u.email,"phone":p.phone,"status":p.status,"email_verified":p.email_verified})

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

def validate_icon_data(value):
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
    if len(raw) > 500 * 1024:
        raise ValueError("L'icône ne doit pas dépasser 500 ko.")
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
        icon_data=validate_icon_data(b.get("icon_data",""))
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
                new_icon=validate_icon_data(b.get("icon_data",""))
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

@require("dev")
def dev_project_stats(request,project_id):
    p=Project.objects.filter(id=project_id,developer=request.api_user).first()
    if not p: return err("Projet introuvable.",404)
    return ok({"project_name":p.name,
               "views":Event.objects.filter(project=p,type="view").count(),
               "visit_clicks":Event.objects.filter(project=p,type="visit_click").count(),
               "installs":Event.objects.filter(project=p,type="install").count() if p.type=="PWA" else None,
               "comments_count":p.comments.count()})

@require("dev")
def dev_project_comments(request,project_id):
    p=Project.objects.filter(id=project_id,developer=request.api_user).first()
    if not p: return err("Projet introuvable.",404)
    return ok([{"id":c.id,"author_name":c.author_name,"content":c.content,"created_at":c.created_at.isoformat()} for c in p.comments.order_by("-created_at")])

@require("dev")
def dev_messages(request):
    if request.method!="GET": return err("Méthode non autorisée.",405)
    return ok([{"id":m.id,"subject":m.subject,"content":m.content,"read":m.read,"created_at":m.created_at.isoformat()} for m in Message.objects.filter(recipient=request.api_user).order_by("-created_at")])

@require("dev")
def dev_message_detail(request,message_id):
    m=Message.objects.filter(id=message_id,recipient=request.api_user).first()
    if not m: return err("Message introuvable.",404)
    if request.method=="GET": return ok({"id":m.id,"subject":m.subject,"content":m.content,"read":m.read,"created_at":m.created_at.isoformat()})
    if request.method=="PATCH":
        if json_body(request).get("read") is True: m.read=True;m.save(update_fields=["read"])
        return ok({"message":"Message mis à jour."})
    return err("Méthode non autorisée.",405)

@require("dev")
def dev_message_reply(request,message_id):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    m=Message.objects.filter(id=message_id,recipient=request.api_user).first()
    if not m: return err("Message introuvable.",404)
    b=json_body(request); content=str(b.get("content","")).strip()
    if not content:return err("Contenu requis.")
    reply=Message.objects.create(sender=request.api_user,recipient=m.sender,subject="Re: "+m.subject,content=content,parent=m)
    return ok({"id":reply.id},201)

@csrf_exempt
def admin_login(request):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    b=json_body(request); email=b.get("email","").strip().lower()
    user=User.objects.filter(email__iexact=email,is_staff=True).first()
    user=authenticate(username=user.username,password=b.get("password","")) if user else None
    if not user: return err("Identifiants invalides.",401)
    return ok({"token":issue_token(user,"admin"),"user":{"id":user.id,"email":user.email,"full_name":user.get_full_name()}})

def admin_only(fn):
    return require("admin")(fn)

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
def admin_dashboard(request):
    qs=Project.objects.all()
    pending=qs.filter(status="EN_ATTENTE")
    return ok({"developers_count":DeveloperProfile.objects.filter(email_verified=True).count(),
               "visitors_count":Visitor.objects.count(),
               "published_count":qs.filter(status="PUBLIE").count(),
               "pending_count":pending.count(),"open_reports_count":Report.objects.filter(status="OUVERT").count(),
               "web_count":qs.filter(type="WEB").count(),"pwa_count":qs.filter(type="PWA").count(),
               "rejected_count":qs.filter(status="REJETE").count(),"suspended_count":qs.filter(status="SUSPENDU").count(),
               "total_project_visits":Event.objects.filter(type="view").count(),
               "total_visit_clicks":Event.objects.filter(type="visit_click").count(),
               "total_installs":Event.objects.filter(type="install").count(),
               "pending_projects":[{"id":p.id,"name":p.name,"developer_name":p.developer.get_full_name() or p.developer.username} for p in pending[:10]]})

@admin_only
def admin_developers(request):
    qs=DeveloperProfile.objects.select_related("user").filter(email_verified=True)
    s=request.GET.get("search","").strip()
    if s: qs=qs.filter(Q(user__username__icontains=s)|Q(user__email__icontains=s)|Q(user__first_name__icontains=s))
    return ok([{"id":p.user.id,"display_name":p.user.get_full_name() or p.user.username,"username":p.user.username,"email":p.user.email,"created_at":p.user.date_joined.isoformat(),"status":p.status} for p in qs.order_by("-user__date_joined")])

@admin_only
def admin_developer_detail(request,user_id):
    if request.method=="DELETE":
        p=DeveloperProfile.objects.select_related("user").filter(user_id=user_id).first()
        if not p: return err("Développeur introuvable.",404)
        p.user.delete()
        return ok(None,204)
    p=DeveloperProfile.objects.select_related("user").filter(user_id=user_id).first()
    if not p:return err("Développeur introuvable.",404)
    u=p.user; projects=Project.objects.filter(developer=u)
    return ok({"id":u.id,"display_name":u.get_full_name() or u.username,"username":u.username,"email":u.email,"created_at":u.date_joined.isoformat(),"status":p.status,
               "projects":[{"id":x.id,"name":x.name,"status":x.status} for x in projects],
               "stats":{"total_views":Event.objects.filter(project__developer=u,type="view").count(),"total_visit_clicks":Event.objects.filter(project__developer=u,type="visit_click").count(),"total_installs":Event.objects.filter(project__developer=u,type="install").count()},
               "reports":[{"project_name":r.project.name,"reason":r.reason} for r in Report.objects.filter(project__developer=u).order_by("-created_at")]})

@admin_only
def admin_developer_suspend(request,user_id):
    if request.method!="POST":return err("Méthode non autorisée.",405)
    p=DeveloperProfile.objects.filter(user_id=user_id).first()
    if not p:return err("Développeur introuvable.",404)
    p.status="SUSPENDU";p.user.is_active=False;p.user.save(update_fields=["is_active"]);p.save(update_fields=["status"])
    return ok({"message":"Compte suspendu."})

@admin_only
def admin_developer_reactivate(request,user_id):
    if request.method!="POST":return err("Méthode non autorisée.",405)
    p=DeveloperProfile.objects.filter(user_id=user_id).first()
    if not p:return err("Développeur introuvable.",404)
    p.status="ACTIF";p.user.is_active=True;p.user.save(update_fields=["is_active"]);p.save(update_fields=["status"])
    return ok({"message":"Compte réactivé."})

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
    return ok({"id":m.id, "email_sent":email_sent},201)

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
    email_sent_count = sum(
        1 for recipient in recipient_list
        if _email_admin_message(recipient, subject, content, request.api_user)
    )
    return ok({
        "message": "Message envoyé à tous les développeurs actifs.",
        "sent_count": len(messages),
        "email_sent_count": email_sent_count,
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
    d["comments"]=[{"id":c.id,"author_name":c.author_name,"content":c.content,"created_at":c.created_at.isoformat()} for c in p.comments.order_by("-created_at")]
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
