# frontend-user — WEB STORE

PWA publique de découverte des projets WEB STORE. Aucun compte visiteur requis.

## Structure

```
frontend-user/
├── index.html          Accueil : recherche, catégories, catalogue
├── offline.html         Page affichée hors ligne par le service worker
├── manifest.json        Manifest PWA (installation Android)
├── service-worker.js    Cache de l'app shell + stratégie réseau pour l'API
├── css/style.css        Feuille de style (palette verte validée)
├── js/api.js            Couche d'accès à l'API Django (WEBSTORE_API_BASE_URL)
├── js/app.js            Logique de rendu, recherche, filtres, installation PWA
├── icons/               Icônes 192×192 et 512×512
└── pages/
    ├── project.html     Fiche détaillée d'un projet (visite, install, commentaires, signalement)
    ├── categories.html  Liste des catégories
    ├── contact.html      Page contact
    └── legal.html        Mentions légales
```

## Configuration

Par défaut, `js/api.js` appelle `/api`. Pour pointer vers un backend déployé
séparément, définir avant le chargement des scripts :

```html
<script>window.WEBSTORE_API_BASE_URL = "https://api.webstore.example.com/api";</script>
```

## Endpoints attendus côté backend

- `GET /categories/`
- `GET /projects/?category=&search=`
- `GET /projects/:slug/`
- `POST /projects/:slug/comments/`
- `POST /projects/:slug/reports/`
- `POST /projects/:slug/events/` (`{ type: "view" | "visit_click" | "install" }`)

## État actuel

Ce module est un frontend fonctionnel et prêt à être branché : sans backend,
il affiche des messages d'indisponibilité clairs plutôt que des données
inventées, conformément aux exigences du cahier des charges (pas de fausses
statistiques, pas de fonctionnalités simulées).

## Déploiement

Fichiers statiques purs (pas de build requis) : déployable sur GitHub Pages,
Netlify, Render (Static Site) ou tout hébergeur de fichiers statiques. Servir
avec HTTPS pour que le service worker et l'installation PWA fonctionnent.
