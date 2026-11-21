"""Notifications Telegram pour les événements de sécurité administrateur."""
import html
import json
import logging
import os
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from django.utils import timezone

logger = logging.getLogger(__name__)


def notify_admin_login(user, request=None):
    """Envoie une alerte non bloquante après l'émission d'un jeton admin."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        logger.warning("Alerte Telegram admin ignorée : variables Telegram absentes.")
        return False

    ip = "inconnue"
    agent = "inconnu"
    if request is not None:
        # REMOTE_ADDR est utilisé plutôt qu'un X-Forwarded-For fourni par le client.
        ip = request.META.get("REMOTE_ADDR") or ip
        agent = request.META.get("HTTP_USER_AGENT", "")[:180] or agent

    timestamp = timezone.localtime().strftime("%d/%m/%Y à %H:%M:%S")
    message = (
        "🔐 <b>WEB STORE — Connexion administrateur</b>\n\n"
        f"Compte : <code>{html.escape(user.email or user.get_username())}</code>\n"
        f"Date : <code>{html.escape(timestamp)}</code>\n"
        f"Adresse IP : <code>{html.escape(ip)}</code>\n"
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
