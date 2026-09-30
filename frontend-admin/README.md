# frontend-admin — WEB STORE

PWA privée pour l'administration générale : modération des publications,
gestion des développeurs, messagerie Admin→Dev. Indépendante du Django
Admin classique (qui peut être conservé côté backend comme outil technique
complémentaire).

Choix de design : thème sombre noir/violet/orange, volontairement distinct
des deux autres PWA, pour une identité "contrôle / modération".

## Sécurité

- **Aucune inscription** dans cette interface : le premier compte admin doit
  être créé côté backend par une commande sécurisée (jamais `admin/admin`,
  jamais d'identifiants en dur).
- Les mots de passe des développeurs ne sont jamais affichés ni transmis à
  cette interface.

## Structure

```
frontend-admin/
├── index.html                  Redirige vers login ou dashboard
├── offline.html
├── manifest.json
├── service-worker.js
├── css/style.css
├── js/api.js                    Client API + token admin (localStorage)
├── js/auth.js
└── pages/
    ├── login.html
    ├── dashboard.html            Vue générale (compteurs globaux)
    ├── developers.html            Liste + recherche des développeurs
    ├── developer-detail.html      Fiche complète : projets, stats, signalements,
    │                              messages, suspendre/réactiver/supprimer
    ├── publications.html          Liste filtrable par statut
    └── publication-detail.html    Approuver / rejeter / suspendre / supprimer
                                    avec motif obligatoire, enregistré
```

## Endpoints attendus côté backend

- `POST /admin/login/`
- `GET /admin/dashboard/`
- `GET /admin/developers/?search=`, `GET /admin/developers/:id/`
- `POST /admin/developers/:id/suspend/`, `POST /admin/developers/:id/reactivate/`
- `DELETE /admin/developers/:id/`
- `POST /admin/developers/:id/messages/`
- `GET /admin/publications/?status=&search=`, `GET /admin/publications/:id/`
- `POST /admin/publications/:id/approve/`
- `POST /admin/publications/:id/reject/` (`{ reason }`)
- `POST /admin/publications/:id/suspend/` (`{ reason }`)
- `DELETE /admin/publications/:id/` (`{ reason }`)

## État actuel

Frontend fonctionnel et prêt à être branché. Sans backend, les compteurs
restent à 0 et les listes affichent un message d'indisponibilité clair —
aucune donnée n'est inventée.

## Déploiement

Fichiers statiques purs, déployables sur GitHub Pages, Netlify ou Render
(Static Site). HTTPS requis. Cette PWA étant sensible, envisager un accès
restreint (VPN, IP allowlist, ou sous-domaine non indexé) en plus de
l'authentification applicative.
