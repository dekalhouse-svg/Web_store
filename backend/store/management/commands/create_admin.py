# Compatibilité avec les anciens déploiements : la commande est désormais idempotente.
# Elle ne réinitialise jamais le mot de passe d'un fondateur déjà enregistré.
from .ensure_founder import Command
