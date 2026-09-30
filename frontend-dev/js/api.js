/**
 * Couche d'accès à l'API WEB STORE pour l'espace développeur.
 * Le token d'authentification est stocké dans localStorage sous "webstore_dev_token"
 * (choix assumé pour une PWA installée : le stockage doit survivre à la fermeture de l'app).
 */

const WebStoreDevAPI = (() => {
  // LOCAL: Django is expected at http://127.0.0.1:8000/api
// PRODUCTION: define window.WEBSTORE_API_BASE_URL before loading this file,
// or replace the local fallback above with your deployed backend /api URL.
const API_BASE_URL = (window.WEBSTORE_API_BASE_URL || "http://127.0.0.1:8000/api").replace(/\/+$/, "");
  const TOKEN_KEY = "webstore_dev_token";

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

    // Authentification
    register: (payload) =>
      request("/dev/register/", { method: "POST", body: JSON.stringify(payload) }),
    verifyEmail: (payload) =>
      request("/dev/verify-email/", { method: "POST", body: JSON.stringify(payload) }),
    resendVerificationCode: (email) =>
      request("/dev/resend-code/", { method: "POST", body: JSON.stringify({ email }) }),
    login: async (payload) => {
      const data = await request("/dev/login/", { method: "POST", body: JSON.stringify(payload) });
      if (data?.token) setToken(data.token);
      return data;
    },
    requestPasswordReset: (email) =>
      request("/dev/password-reset/", { method: "POST", body: JSON.stringify({ email }) }),
    confirmPasswordReset: (payload) =>
      request("/dev/password-reset/confirm/", { method: "POST", body: JSON.stringify(payload) }),

    // Profil
    getMe: () => request("/dev/me/"),

    // Vue générale
    getDashboardStats: () => request("/dev/dashboard/"),

    // Projets
    getProjects: () => request("/dev/projects/"),
    getProject: (id) => request(`/dev/projects/${id}/`),
    createProject: (payload) =>
      request("/dev/projects/", { method: "POST", body: JSON.stringify(payload) }),
    updateProject: (id, payload) =>
      request(`/dev/projects/${id}/`, { method: "PUT", body: JSON.stringify(payload) }),
    deleteProject: (id) => request(`/dev/projects/${id}/`, { method: "DELETE" }),
    getProjectStats: (id) => request(`/dev/projects/${id}/stats/`),
    getProjectComments: (id) => request(`/dev/projects/${id}/comments/`),

    // Messagerie
    getMessages: () => request("/dev/messages/"),
    getMessage: (id) => request(`/dev/messages/${id}/`),
    markMessageRead: (id) =>
      request(`/dev/messages/${id}/`, { method: "PATCH", body: JSON.stringify({ read: true }) }),
    replyToMessage: (id, content) =>
      request(`/dev/messages/${id}/reply/`, { method: "POST", body: JSON.stringify({ content }) }),
  };
})();
