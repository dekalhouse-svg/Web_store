/**
 * WEB STORE Dev — Service Worker
 *
 * Pour publier une mise à jour chez TOUS les développeurs :
 *   1. modifie ce que tu veux dans le projet,
 *   2. change la valeur de VERSION ci-dessous (une seule ligne),
 *   3. déploie.
 * À leur prochaine ouverture (ou dès qu'ils reviennent sur l'app), la nouvelle
 * version est détectée, installée et appliquée automatiquement.
 *
 * Même si VERSION n'est pas changée, les fichiers sont toujours récupérés
 * sur le réseau en premier : le cache ne sert que quand on est hors ligne.
 */
const VERSION = "2026.10.20-1";

const CACHE_PREFIX = "webstore-dev-";
const CACHE_NAME = CACHE_PREFIX + VERSION;
const NETWORK_TIMEOUT_MS = 4000; // réseau trop lent → on affiche la copie en cache

const APP_SHELL = [
  "/index.html",
  "/offline.html",
  "/manifest.json",
  "/css/style.css",
  "/js/config.js",
  "/js/updater.js",
  "/js/api.js",
  "/js/auth.js",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/pages/login.html",
  "/pages/register.html",
  "/pages/verify-email.html",
  "/pages/forgot-password.html",
  "/pages/reset-password.html",
  "/pages/dashboard.html",
  "/pages/projects.html",
  "/pages/project-form.html",
  "/pages/project-stats.html",
  "/pages/messages.html"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      // cache: "reload" → on ignore le cache HTTP de l'hébergeur pour avoir les vrais fichiers neufs
      Promise.allSettled(APP_SHELL.map((url) => cache.add(new Request(url, { cache: "reload" }))))
    )
  );
  self.skipWaiting(); // la nouvelle version prend la main tout de suite
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return; // jamais de cache sur les requêtes d'authentification

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // l'API (Render, etc.) n'est jamais interceptée
  if (url.pathname.startsWith("/api/")) return;

  event.respondWith(networkFirst(event, request, url));
});

/* ---------------------------------------------------------------------- */

function cacheKey(url) {
  // On ignore ?id=3 etc. pour ne pas multiplier les copies d'une même page
  let path = url.pathname;
  if (path.endsWith("/")) path += "index.html";
  return url.origin + path;
}

async function matchCache(key) {
  const cache = await caches.open(CACHE_NAME);
  return cache.match(key);
}

// Certains hébergeurs redirigent (ex. /page → /page.html) ; une réponse « redirected »
// ne peut pas être servie telle quelle à une navigation : on en recrée une propre.
async function cleanRedirect(response) {
  if (!response.redirected) return response;
  const body = await response.blob();
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers
  });
}

async function offlineResponse(request) {
  if (request.mode === "navigate") {
    const offline = await matchCache(new URL("/offline.html", self.location.origin).href);
    if (offline) return offline;
  }
  return new Response("", { status: 503, statusText: "Hors ligne" });
}

async function networkFirst(event, request, url) {
  const key = cacheKey(url);
  // no-cache : on demande toujours au serveur « as-tu changé ? » (304 si rien de nouveau)
  const freshRequest = new Request(request.url, { cache: "no-cache", credentials: "same-origin" });

  const fromNetwork = fetch(freshRequest).then(async (response) => {
    const clean = await cleanRedirect(response);
    if (clean.ok) {
      const copy = clean.clone();
      await caches
        .open(CACHE_NAME)
        .then((cache) => cache.put(key, copy))
        .catch(() => {});
    }
    return clean;
  });

  // Garde le service worker en vie pour finir la mise à jour du cache, même si la copie a été servie avant
  event.waitUntil(fromNetwork.catch(() => {}));

  // Réseau trop lent : on sert la copie en cache si elle existe, sinon on continue d'attendre le réseau
  const slowFallback = new Promise((resolve) => {
    setTimeout(async () => {
      const cached = await matchCache(key);
      if (cached) resolve(cached);
    }, NETWORK_TIMEOUT_MS);
  });

  try {
    return await Promise.race([fromNetwork, slowFallback]);
  } catch (err) {
    // Hors ligne
    return (await matchCache(key)) || offlineResponse(request);
  }
}
