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
