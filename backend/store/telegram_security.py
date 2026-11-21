"""Notifications Telegram pour les événements de sécurité administrateur."""
import html
import ipaddress
import json
import logging
import os
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from django.utils import timezone

logger = logging.getLogger(__name__)


def _client_ip(request):
    """Retourne l'IP client fournie par le proxy de confiance de Render."""
    if request is None:
        return ""
    # Render recommande X-Forwarded-For pour retrouver l'IP du visiteur derrière
    # ses proxies. CF-Connecting-IP est prioritaire lorsqu'il est fourni.
    candidates = []
    cf_ip = request.META.get("HTTP_CF_CONNECTING_IP", "").strip()
    if cf_ip:
        candidates.append(cf_ip)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidates.extend(part.strip() for part in forwarded.split(",") if part.strip())
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.is_global:
            return str(address)
    return ""


def _ip_location(ip):
    """Recherche la ville et le pays à partir de l'IP (résultat approximatif)."""
    if not ip:
        return "Ville/pays indisponibles"
    try:
        address = ipaddress.ip_address(ip)
        if not address.is_global:
            return "IP privée ou locale (position indisponible)"
        req = Request(
            f"https://ipwho.is/{ip}",
            headers={"Accept": "application/json", "User-Agent": "WEB-STORE-Security/1.0"},
            method="GET",
        )
        with urlopen(req, timeout=2.5) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result.get("success") is False:
            return "Ville/pays indisponibles"
        city = str(result.get("city") or "").strip()
        country = str(result.get("country") or "").strip()
        if city and country:
            return f"{city}, {country}"
        if country:
            return country
    except (URLError, HTTPError, TimeoutError, ValueError, OSError):
        logger.info("Géolocalisation IP indisponible pour l'alerte Telegram.")
    return "Ville/pays indisponibles"


def notify_admin_login(user, request=None):
    """Envoie une alerte non bloquante après l'émission d'un jeton admin."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        logger.warning("Alerte Telegram admin ignorée : variables Telegram absentes.")
        return False

    ip = _client_ip(request) or "inconnue"
    agent = "inconnu"
    if request is not None:
        agent = request.META.get("HTTP_USER_AGENT", "")[:180] or agent
    location = _ip_location(ip)

    timestamp = timezone.localtime().strftime("%d/%m/%Y à %H:%M:%S")
    message = (
        "🔐 <b>WEB STORE — Connexion administrateur</b>\n\n"
        f"Compte : <code>{html.escape(user.email or user.get_username())}</code>\n"
        f"Date : <code>{html.escape(timestamp)}</code>\n"
        f"Adresse IP : <code>{html.escape(ip)}</code>\n"
        f"Lieu estimé : <code>{html.escape(location)}</code>\n"
        f"Appareil : <code>{html.escape(agent)}</code>\n\n"
        "⚠️ Si tu n'es pas à l'origine de cette connexion, sécurise immédiatement ton compte."
    )
    payload = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}).encode("utf-8")
    req = Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=4) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result.get("ok"):
            return True
        logger.warning("Telegram a refusé l'alerte de connexion administrateur.")
    except (URLError, HTTPError, TimeoutError, ValueError, OSError):
        logger.exception("Échec de l'envoi de l'alerte Telegram administrateur.")
    return False
