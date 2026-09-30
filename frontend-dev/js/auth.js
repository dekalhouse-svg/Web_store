/**
 * Protège les pages du dashboard : redirige vers login.html si aucun token
 * n'est présent. À inclure sur chaque page nécessitant une session.
 */
(function guardPage() {
  const isAuthPage = /\/(login|register|verify-email|forgot-password|reset-password)\.html$/.test(
    window.location.pathname
  );

  if (!isAuthPage && !WebStoreDevAPI.isAuthenticated()) {
    window.location.href = "/pages/login.html";
  }

  if (isAuthPage && WebStoreDevAPI.isAuthenticated() && !/verify-email/.test(window.location.pathname)) {
    window.location.href = "/pages/dashboard.html";
  }
})();

function bindLogout() {
  const btn = document.getElementById("logoutBtn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    WebStoreDevAPI.logout();
    window.location.href = "/pages/login.html";
  });
}

function bindSidebarToggle() {
  const toggle = document.getElementById("menuToggle");
  const sidebar = document.getElementById("sidebar");
  if (!toggle || !sidebar) return;
  toggle.addEventListener("click", () => sidebar.classList.toggle("open"));
}

document.addEventListener("DOMContentLoaded", () => {
  bindLogout();
  bindSidebarToggle();
  registerServiceWorker();
});

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  const swPath = window.location.pathname.includes("/pages/") ? "../service-worker.js" : "service-worker.js";
  navigator.serviceWorker.register(swPath).catch(() => {});
}
