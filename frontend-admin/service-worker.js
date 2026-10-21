/* WEB STORE Admin PWA: privilégie le réseau pour ne pas servir indéfiniment une ancienne interface. */
const CACHE_NAME = "webstore-admin-v4";
const APP_SHELL = [
  "/index.html",
  "/offline.html",
  "/css/style.css",
  "/js/config.js",
  "/js/api.js",
  "/js/auth.js",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/pages/login.html",
  "/pages/dashboard.html",
  "/pages/messages.html",
  "/pages/profile.html",
  "/pages/developers.html",
  "/pages/publications.html"
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    // Une page optionnelle absente ne doit pas bloquer toute la mise à jour.
    await Promise.all(APP_SHELL.map(async (path) => {
      try {
        const response = await fetch(path, { cache: "reload" });
        if (response.ok) await cache.put(path, response);
      } catch (_) {}
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key.startsWith("webstore-admin-") && key !== CACHE_NAME)
      .map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  // Ne jamais mettre en cache les API, les requêtes externes ou les données dynamiques.
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const response = await fetch(request, { cache: "no-store" });
        if (response && response.ok) {
          const cache = await caches.open(CACHE_NAME);
          await cache.put(request, response.clone());
        }
        return response;
      } catch (_) {
        return (await caches.match(request)) || (await caches.match("/offline.html"));
      }
    })());
    return;
  }

  // Réseau d'abord pour CSS, JS, icônes et manifest; cache uniquement hors ligne.
  event.respondWith((async () => {
    try {
      const response = await fetch(request, { cache: "no-store" });
      if (response && response.ok) {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(request, response.clone());
      }
      return response;
    } catch (_) {
      return await caches.match(request) || Response.error();
    }
  })());
});
