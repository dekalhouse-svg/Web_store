# frontend-dev — WEB STORE

PWA réservée aux développeurs : inscription, vérification e-mail, connexion,
récupération de mot de passe, dashboard, gestion de projets, statistiques par
projet et messagerie reçue de l'administration.

## Structure

```
frontend-dev/
├── index.html              Redirige vers login ou dashboard selon la session
├── offline.html
├── manifest.json
├── service-worker.js
├── css/style.css           Layout dashboard (sidebar sombre) distinct de frontend-user
├── js/api.js                Client API + gestion du token (localStorage)
├── js/auth.js                Garde de session, déconnexion, menu mobile
└── pages/
    ├── register.html
    ├── verify-email.html
    ├── login.html
    ├── forgot-password.html
    ├── reset-password.html
    ├── dashboard.html
    ├── projects.html
    ├── project-form.html     Ajout / modification d'un projet
    ├── project-stats.html    Statistiques d'un projet (distingue clairement
    │                          visites Web Store / clics externes / installs)
    └── messages.html          Boîte de réception (Admin → Dev)
```

## Authentification

Le token renvoyé par `POST /api/dev/login/` est stocké dans
`localStorage["webstore_dev_token"]` et envoyé en `Authorization: Bearer`.
Toute réponse `401` déconnecte l'utilisateur et le renvoie vers `login.html`.

## Configuration

```html
<script>window.WEBSTORE_API_BASE_URL = "https://api.webstore.example.com/api";</script>
```

## Endpoints attendus côté backend

- `POST /dev/register/`, `POST /dev/verify-email/`, `POST /dev/resend-code/`
- `POST /dev/login/`
- `POST /dev/password-reset/`, `POST /dev/password-reset/confirm/`
- `GET /dev/me/`, `GET /dev/dashboard/`
- `GET|POST /dev/projects/`, `GET|PUT|DELETE /dev/projects/:id/`
- `GET /dev/projects/:id/stats/`, `GET /dev/projects/:id/comments/`
- `GET /dev/messages/`, `GET|PATCH /dev/messages/:id/`, `POST /dev/messages/:id/reply/`

## État actuel

Frontend fonctionnel et prêt à être branché. Sans backend, les cartes de
statistiques affichent 0 (jamais de données inventées) et les listes affichent
un message d'indisponibilité clair.

## Déploiement

Fichiers statiques purs, déployables sur GitHub Pages, Netlify ou Render
(Static Site). HTTPS requis pour le service worker et l'installation PWA.


## Mise à jour de l’espace développeur — 19 novembre 2026

Cette mise à jour est incrémentale : seuls les fichiers présents dans l’archive de correctif doivent être ajoutés ou remplacés dans leurs chemins respectifs.

### Déploiement
1. Copier les fichiers `backend/` vers le dépôt backend.
2. Exécuter `python manage.py migrate` dans le service backend pour ajouter `DeveloperProfile.avatar_data`.
3. Déployer les fichiers `frontend-dev/` sur l’hébergement du frontend développeur.
4. Vérifier la connexion, le profil, l’ajout/suppression de photo, les statistiques, les projets et les messages.

La photo de profil est redimensionnée dans le navigateur puis enregistrée sous forme de donnée image dans le profil développeur. Elle est privée et n’est pas ajoutée à la fiche publique du développeur.

Les notifications de la nouvelle page sont une synthèse des messages et statuts de projets actuellement disponibles. Elles ne constituent pas encore un système de notifications push ni un historique persistant dédié.
