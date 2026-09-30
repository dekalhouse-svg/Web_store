# WEB STORE 1.0 — Version corrigée

Cette version contient exactement quatre dossiers racine :

- `frontend-user/` — interface publique utilisateur
- `frontend-dev/` — espace développeur
- `frontend-admin/` — espace administration
- `backend/` — API Django

## 1. Tester en local

### Backend
```bash
cd backend
python -m venv .venv
# Linux/Termux:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_categories
python manage.py create_admin
python manage.py runserver 127.0.0.1:8000
```

API locale : `http://127.0.0.1:8000`
API : `http://127.0.0.1:8000/api/`

### Frontend user
Dans un autre terminal :
```bash
cd frontend-user
python -m http.server 5500
```
Puis ouvrir `http://127.0.0.1:5500/`.

### Frontend dev
```bash
cd frontend-dev
python -m http.server 5501
```
Puis ouvrir `http://127.0.0.1:5501/`.

### Frontend admin
```bash
cd frontend-admin
python -m http.server 5502
```
Puis ouvrir `http://127.0.0.1:5502/`.

> Ne pas ouvrir les fichiers HTML directement avec `file://`. Utilisez un petit serveur HTTP comme ci-dessus.

## 2. Où remplacer l'URL locale après publication

Il n'y a que **3 fichiers principaux** à modifier :

- `frontend-user/js/config.js`
- `frontend-dev/js/config.js`
- `frontend-admin/js/config.js`

Ils contiennent actuellement :

`http://127.0.0.1:8000/api`

Après déploiement, remplacez cette valeur par l'URL API réelle de votre backend, par exemple :

`https://votre-backend.example.com/api`

Les fichiers `js/api.js` lisent automatiquement cette configuration. Il n'est donc pas nécessaire de modifier chaque appel API.

## 3. Vérification e-mail

La V1 est volontairement configurée avec :

`REQUIRE_EMAIL_VERIFICATION=false`

Le champ et les routes de vérification sont déjà présents afin de préparer la V2.

Lorsque votre service de messagerie sera prêt, vous pourrez configurer les variables SMTP dans l'environnement du backend et passer :

`REQUIRE_EMAIL_VERIFICATION=true`

Les routes déjà préparées sont notamment :
- `/api/dev/verify-email/`
- `/api/dev/resend-code/`
- `/api/dev/password-reset/`
- `/api/dev/password-reset/confirm/`

## 4. Compte administrateur

Le formulaire admin ne crée pas de compte. Le premier compte est créé côté backend :

```bash
python manage.py create_admin
```

Puis connexion depuis `frontend-admin`.

## 5. Déploiement

Déployez `backend/` comme service Python/Django.

Les trois frontends peuvent être déployés séparément. Après obtention de l'URL du backend, modifiez uniquement les trois `js/config.js` indiqués ci-dessus.

## 6. Important

La base SQLite `db.sqlite3` est conservée pour les tests locaux. Pour une production importante, prévoyez une base de données persistante adaptée à votre hébergeur.
