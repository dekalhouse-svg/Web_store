(function guardPage() {
  const isLoginPage = window.location.pathname.endsWith("/login.html");

  if (!isLoginPage && !WebStoreAdminAPI.isAuthenticated()) {
    window.location.href = "/pages/login.html";
  }

  if (isLoginPage && WebStoreAdminAPI.isAuthenticated()) {
    window.location.href = "/pages/dashboard.html";
  }
})();

function bindLogout() {
  const btn = document.getElementById("logoutBtn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    WebStoreAdminAPI.logout();
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
