/**
 * Couche d'accès à l'API WEB STORE pour l'administration.
 * Aucune inscription ici : le premier compte admin est créé de façon sécurisée
 * côté backend (commande de management Django), jamais via cette interface.
 */

const WebStoreAdminAPI = (() => {
  // LOCAL: Django is expected at http://127.0.0.1:8000/api
// PRODUCTION: define window.WEBSTORE_API_BASE_URL before loading this file,
// or replace the local fallback above with your deployed backend /api URL.
const API_BASE_URL = (window.WEBSTORE_API_BASE_URL || "http://127.0.0.1:8000/api").replace(/\/+$/, "");
  const TOKEN_KEY = "webstore_admin_token";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token) {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  }

  async function request(path, options = {}) {
    const token = getToken();
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const response = await fetch(`${API_BASE_URL}${normalizedPath}`, {
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...options,
    });

    if (response.status === 401) {
      setToken(null);
      if (!location.pathname.endsWith("/login.html")) {
        window.location.href = "login.html";
      }
      throw new Error("Session expirée");
    }

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Erreur API (${response.status})`);
    }

    if (response.status === 204) return null;
    return response.json();
  }

  return {
    isAuthenticated: () => Boolean(getToken()),
    logout: () => setToken(null),

    login: async (payload) => {
      const data = await request("/admin/login/", { method: "POST", body: JSON.stringify(payload) });
      if (data?.token) setToken(data.token);
      return data;
    },

    // Vue générale
    getDashboardStats: () => request("/admin/dashboard/"),

    // Développeurs
    getDevelopers: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/admin/developers/${query ? `?${query}` : ""}`);
    },
    getDeveloper: (id) => request(`/admin/developers/${id}/`),
    suspendDeveloper: (id) => request(`/admin/developers/${id}/suspend/`, { method: "POST" }),
    reactivateDeveloper: (id) => request(`/admin/developers/${id}/reactivate/`, { method: "POST" }),
    deleteDeveloper: (id) => request(`/admin/developers/${id}/`, { method: "DELETE" }),
    sendMessageToDeveloper: (id, payload) =>
      request(`/admin/developers/${id}/messages/`, { method: "POST", body: JSON.stringify(payload) }),

    // Publications
    getPublications: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/admin/publications/${query ? `?${query}` : ""}`);
    },
    getPublication: (id) => request(`/admin/publications/${id}/`),
    approvePublication: (id) => request(`/admin/publications/${id}/approve/`, { method: "POST" }),
    setFeatured: (id, featured) => request(`/admin/publications/${id}/feature/`, { method: "POST", body: JSON.stringify({ featured }) }),
    rejectPublication: (id, reason) =>
      request(`/admin/publications/${id}/reject/`, { method: "POST", body: JSON.stringify({ reason }) }),
    suspendPublication: (id, reason) =>
      request(`/admin/publications/${id}/suspend/`, { method: "POST", body: JSON.stringify({ reason }) }),
    deletePublication: (id, reason) =>
      request(`/admin/publications/${id}/`, { method: "DELETE", body: JSON.stringify({ reason }) }),
  };
})();
