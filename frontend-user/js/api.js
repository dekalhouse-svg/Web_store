/**
 * Couche d'accès à l'API WEB STORE.
 * Toutes les URLs passent par API_BASE_URL, à définir selon l'environnement
 * (voir config ci-dessous). Aucune donnée n'est inventée : tant que le
 * backend n'est pas branché, les fonctions renvoient un tableau/objet vide
 * plutôt que des statistiques ou projets fictifs.
 */

const WebStoreAPI = (() => {
  // À adapter en production (ex: https://api.webstore.app)
  // LOCAL: Django is expected at http://127.0.0.1:8000/api
// PRODUCTION: define window.WEBSTORE_API_BASE_URL before loading this file,
// or replace the local fallback above with your deployed backend /api URL.
const API_BASE_URL = (window.WEBSTORE_API_BASE_URL || "http://127.0.0.1:8000/api").replace(/\/+$/, "");

  async function request(path, options = {}) {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const response = await fetch(`${API_BASE_URL}${normalizedPath}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });

    if (!response.ok) {
      throw new Error(`Erreur API (${response.status}) sur ${path}`);
    }

    if (response.status === 204) return null;
    return response.json();
  }

  return {
    // Visiteur anonyme : aucun compte ni information personnelle requis.
    trackVisitor: async () => {
      let visitorId = localStorage.getItem("webstore_visitor_id");
      const headers = visitorId ? { "X-Visitor-ID": visitorId } : {};
      const data = await request("/visitors/track/", { method: "POST", headers });
      if (data?.visitor_id) localStorage.setItem("webstore_visitor_id", data.visitor_id);
      return data;
    },

    // Catalogue
    getCategories: () => request("/categories/"),
    getProjects: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/projects/${query ? `?${query}` : ""}`);
    },
    getProject: (slug) => request(`/projects/${slug}/`),

    // Interactions publiques (sans compte)
    postComment: (slug, payload) =>
      request(`/projects/${slug}/comments/`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    postReport: (slug, payload) =>
      request(`/projects/${slug}/reports/`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    // Analytics respectueuses de la vie privée : un simple événement, pas de
    // profilage. Échoue silencieusement pour ne jamais bloquer l'UI.
    trackEvent: (slug, eventType) =>
      request(`/projects/${slug}/events/`, {
        method: "POST",
        body: JSON.stringify({ type: eventType }),
      }).catch(() => null),
  };
})();
