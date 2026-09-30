import hashlib, secrets
from functools import wraps
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.text import slugify
from .models import DeveloperProfile, Category, Project, Comment, Report, Event, AuthToken, Message, ModerationLog, Visitor

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

def project_public(p):
    return {"id":p.id,"name":p.name,"slug":p.slug,"description":p.description,"url":p.url,
            "type":p.type,"category":p.category,"category_slug":slugify(p.category) if p.category else "all","tags":p.tags,"status":p.status,"featured":p.featured,
            "developer_id":p.developer_id,"developer_name":p.developer.get_full_name() or p.developer.username,
            "created_at":p.created_at.isoformat()}

def project_detail_public(p):
    d=project_public(p)
    d["comments"]=[{"id":c.id,"author_name":c.author_name,"content":c.content,"created_at":c.created_at.isoformat()} for c in p.comments.order_by("-created_at")]
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

@csrf_exempt
def public_projects(request):
    if request.method!="GET": return err("Méthode non autorisée.",405)
    qs=Project.objects.filter(status__in=["EN_ATTENTE", "PUBLIE"]).select_related("developer")
    search=request.GET.get("search","").strip()
    category=request.GET.get("category","").strip()
    if search: qs=qs.filter(Q(name__icontains=search)|Q(description__icontains=search)|Q(tags__icontains=search))
    if category: qs=qs.filter(category__iexact=category)
    return ok([project_public(p) for p in qs.order_by("-featured", "-created_at")])

@csrf_exempt
def public_project(request,slug):
    if request.method!="GET": return err("Méthode non autorisée.",405)
    p=Project.objects.select_related("developer").filter(slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]).first()
    if not p: return err("Projet introuvable.",404)
    return ok(project_detail_public(p))

@csrf_exempt
def project_comments(request,slug):
    p=Project.objects.filter(slug=slug, status__in=["EN_ATTENTE", "PUBLIE"]).first()
    if not p: return err("Projet introuvable.",404)
    if request.method=="GET": return ok([{"id":c.id,"author_name":c.author_name,"content":c.content,"created_at":c.created_at.isoformat()} for c in p.comments.order_by("-created_at")])
    if request.method=="POST":
        b=json_body(request); name=str(b.get("author_name","")).strip(); content=str(b.get("content","")).strip()
        if not name or not content: return err("Nom et commentaire requis.")
        c=Comment.objects.create(project=p,author_name=name[:100],content=content[:2000])
        return ok({"id":c.id,"author_name":c.author_name,"content":c.content,"created_at":c.created_at.isoformat()},201)
    return err("Méthode non autorisée.",405)

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

def send_verification_email(user, code):
    from django.core.mail import send_mail
    send_mail(
        "WEB STORE — Vérification de votre e-mail",
        f"Votre code de vérification WEB STORE est : {code}",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=True,
    )

@csrf_exempt
def dev_register(request):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    b=json_body(request); full=b.get("full_name","").strip(); username=b.get("username","").strip()
    email=b.get("email","").strip().lower(); phone=b.get("phone","").strip(); password=b.get("password","")
    if not all([full,username,email,password]): return err("Nom, username, e-mail et mot de passe requis.")
    if User.objects.filter(Q(username__iexact=username)|Q(email__iexact=email)).exists(): return err("Ce compte existe déjà.",409)
    user=User.objects.create_user(username=username,email=email,password=password,first_name=full)
    code=f"{secrets.randbelow(1000000):06d}"
    profile = DeveloperProfile.objects.create(
        user=user,
        phone=phone,
        verification_code=code if getattr(settings, "REQUIRE_EMAIL_VERIFICATION", False) else "",
        code_created_at=timezone.now() if getattr(settings, "REQUIRE_EMAIL_VERIFICATION", False) else None,
        email_verified=not getattr(settings, "REQUIRE_EMAIL_VERIFICATION", False),
    )
    if getattr(settings, "REQUIRE_EMAIL_VERIFICATION", False):
        send_verification_email(user, code)
        data={"message":"Compte créé. Vérifiez votre e-mail pour obtenir le code."}
        if settings.DEBUG: data["verification_code"]=code
    else:
        data={"message":"Compte créé. Vous pouvez maintenant vous connecter."}
    return ok(data,201)

@csrf_exempt
def dev_verify_email(request):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    b=json_body(request); email=b.get("email","").strip().lower(); code=b.get("code","").strip()
    user=User.objects.filter(email__iexact=email).first()
    if not user: return err("Code invalide.",400)
    profile=getattr(user,"developer_profile",None)
    if not profile or profile.verification_code!=code: return err("Code invalide.",400)
    profile.email_verified=True; profile.verification_code=""; profile.save(update_fields=["email_verified","verification_code"])
    return ok({"message":"E-mail vérifié."})

@csrf_exempt
def dev_resend_code(request):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    email=json_body(request).get("email","").strip().lower()
    user=User.objects.filter(email__iexact=email).first()
    if not user: return ok({"message":"Si le compte existe, un nouveau code a été généré."})
    profile=getattr(user,"developer_profile",None)
    if profile:
        code=f"{secrets.randbelow(1000000):06d}"; profile.verification_code=code; profile.code_created_at=timezone.now(); profile.save(update_fields=["verification_code","code_created_at"])
        data={"message":"Nouveau code généré."}
        from django.conf import settings
        if settings.DEBUG: data["verification_code"]=code
        return ok(data)
    return ok({"message":"Si le compte existe, un nouveau code a été généré."})

@csrf_exempt
def dev_login(request):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    b=json_body(request); user=authenticate(username=User.objects.filter(email__iexact=b.get("email","").strip()).values_list("username",flat=True).first() or "",password=b.get("password",""))
    if not user or not hasattr(user,"developer_profile"): return err("Identifiants invalides.",401)
    p=user.developer_profile
    if p.status!="ACTIF": return err("Compte non actif.",401)
    if getattr(settings, "REQUIRE_EMAIL_VERIFICATION", False) and not p.email_verified:
        return err("E-mail non vérifié.",401)
    return ok({"token":issue_token(user,"dev"),"user":{"id":user.id,"username":user.username,"email":user.email,"full_name":user.get_full_name()}})

@csrf_exempt
def dev_password_reset(request):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    email=json_body(request).get("email","").strip().lower(); user=User.objects.filter(email__iexact=email).first()
    if user and hasattr(user,"developer_profile"):
        code=f"{secrets.randbelow(1000000):06d}"; p=user.developer_profile; p.reset_code=code;p.code_created_at=timezone.now();p.save(update_fields=["reset_code","code_created_at"])
        from django.core.mail import send_mail
        send_mail(
            "WEB STORE — Réinitialisation du mot de passe",
            f"Votre code de réinitialisation WEB STORE est : {code}",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True,
        )
        if settings.DEBUG:
            return ok({"message":"Si un compte existe pour cette adresse, un code a été généré.","reset_code":code})
    return ok({"message":"Si un compte existe pour cette adresse, un code de réinitialisation vient d'être envoyé."})

@csrf_exempt
def dev_password_reset_confirm(request):
    if request.method!="POST": return err("Méthode non autorisée.",405)
    b=json_body(request); email=b.get("email","").strip().lower(); code=b.get("code","").strip(); pw=b.get("new_password","")
    user=User.objects.filter(email__iexact=email).first()
    if not user or not hasattr(user,"developer_profile") or user.developer_profile.reset_code!=code: return err("Code invalide.",400)
    user.set_password(pw); user.save(); user.developer_profile.reset_code=""; user.developer_profile.save(update_fields=["reset_code"])
    return ok({"message":"Mot de passe mis à jour."})

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

def create_dev_project(u,b):
    name=str(b.get("name","")).strip(); url=str(b.get("url","")).strip()
    if not name or not url: return err("Nom et URL requis.")
    p=Project.objects.create(developer=u,name=name,slug=unique_slug(name),description=str(b.get("description","")).strip(),
        url=url,type=b.get("type","WEB"),category=str(b.get("category","")).strip(),tags=b.get("tags",[]),status="EN_ATTENTE")
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
        p.save(); return ok(dev_project_payload(p))
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

@admin_only
def admin_dashboard(request):
    qs=Project.objects.all()
    pending=qs.filter(status="EN_ATTENTE")
    return ok({"developers_count":DeveloperProfile.objects.count(),
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
    qs=DeveloperProfile.objects.select_related("user").all()
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

@admin_only
def admin_developer_message(request,user_id):
    if request.method!="POST":return err("Méthode non autorisée.",405)
    recipient=User.objects.filter(id=user_id).first()
    if not recipient:return err("Développeur introuvable.",404)
    b=json_body(request); subject=str(b.get("subject","")).strip();content=str(b.get("content","")).strip()
    if not subject or not content:return err("Sujet et contenu requis.")
    m=Message.objects.create(sender=request.api_user,recipient=recipient,subject=subject,content=content)
    return ok({"id":m.id},201)

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
    d["comments"]=[{"author_name":c.author_name,"content":c.content} for c in p.comments.order_by("-created_at")]
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

