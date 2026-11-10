const CACHE_NAME = "webstore-user-v11";
const APP_SHELL = [
  "./", "./index.html", "./animation.html", "./offline.html",
  "./css/style.css", "./js/app.js", "./js/config.js", "./js/api.js",
  "./pages/project.html", "./pages/categories.html", "./pages/contact.html",
  "./pages/developer.html", "./manifest.json", "./icons/icon-192.png", "./icons/icon-512.png"
];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)).catch(() => {}));
  self.skipWaiting();
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("webstore-user-") && key !== CACHE_NAME).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const req = event.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (req.mode === "navigate" || req.destination === "document") {
    event.respondWith(fetch(req, {cache:"no-cache"}).then(res => {
      if (res.ok) { const copy=res.clone(); caches.open(CACHE_NAME).then(c=>c.put(req,copy)); }
      return res;
    }).catch(async () => {
      const cached = await caches.match(req);
      if (cached) return cached;
      return (await caches.match("./offline.html")) || new Response("Vous êtes hors ligne.", {headers:{"Content-Type":"text/plain; charset=utf-8"}});
    }));
    return;
  }
  event.respondWith(fetch(req, {cache:"no-cache"}).then(res => {
    if (res.ok) { const copy=res.clone(); caches.open(CACHE_NAME).then(c=>c.put(req,copy)); }
    return res;
  }).catch(async () => (await caches.match(req)) || Response.error()));
});
