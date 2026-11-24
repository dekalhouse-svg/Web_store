# WEB STORE Backend

Backend Django de WEB STORE.

Local:
`http://127.0.0.1:8000`

API:
`http://127.0.0.1:8000/api/`

Commandes:
```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_categories
python manage.py create_admin
python manage.py runserver 127.0.0.1:8000
```

## E-mail V1 / V2

V1:
`REQUIRE_EMAIL_VERIFICATION=false`

V2:
`REQUIRE_EMAIL_VERIFICATION=true`

SMTP préparé via:
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- `EMAIL_USE_SSL`
- `DEFAULT_FROM_EMAIL`

Sans SMTP configuré, Django utilise la console.


## Notifications persistantes et Web Push

Les messages envoyés par l'administration sont désormais enregistrés aussi dans le centre de notifications du développeur. La migration `0017_notifications_push_subscriptions` crée les notifications et les abonnements push. Le déploiement habituel exécute déjà `python manage.py migrate`.

Les notifications internes fonctionnent sans configuration supplémentaire. Pour les notifications dans la barre du téléphone, configurer dans l'environnement du backend une paire de clés VAPID :

- `WEBPUSH_VAPID_PUBLIC_KEY` : clé publique VAPID au format Base64 URL-safe.
- `WEBPUSH_VAPID_PRIVATE_KEY` : clé privée VAPID acceptée par pywebpush.
- `WEBPUSH_VAPID_SUBJECT` : adresse de contact, par exemple `mailto:dekalhouse@gmail.com`.

Après configuration, le développeur active explicitement les notifications dans sa page « Notifications ». Sans clés VAPID, les notifications restent consultables dans WEB STORE, mais aucun push système n'est envoyé. Ne jamais placer la clé privée dans le frontend ni dans le dépôt Git.
