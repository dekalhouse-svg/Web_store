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
  setupMessagesNavigation();
  registerServiceWorker();
});

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  const swPath = window.location.pathname.includes("/pages/") ? "../service-worker.js" : "service-worker.js";
  navigator.serviceWorker.register(swPath).catch(() => {});
}


function setupMessagesNavigation() {
  const nav = document.querySelector(".sidebar-nav");
  if (!nav || !WebStoreAdminAPI.isAuthenticated()) return;
  let link = nav.querySelector('a[data-webstore-messages="admin"]');
  if (!link) {
    link = document.createElement("a");
    link.href = "messages.html";
    link.dataset.webstoreMessages = "admin";
    link.textContent = "Messages";
    const current = window.location.pathname.split("/").pop();
    if (current === "messages.html") link.classList.add("active");
    nav.appendChild(link);
  }
  let badge = link.querySelector(".message-unread-badge");
  if (!badge) { badge = document.createElement("span"); badge.className = "message-unread-badge"; badge.style.cssText = "display:none;float:right;min-width:18px;padding:1px 5px;border-radius:10px;background:#dc2626;color:#fff;font-size:12px;text-align:center"; link.appendChild(badge); }
  const refresh = async () => {
    try { const items = await WebStoreAdminAPI.getMessages("inbox"); const count = items.filter(m => !m.read).length; badge.textContent = count > 99 ? "99+" : String(count); badge.style.display = count ? "inline-block" : "none"; } catch (_) {}
  };
  refresh(); window.setInterval(refresh, 30000);
}
