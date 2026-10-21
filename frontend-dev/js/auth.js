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
  setupMessagesNavigation();
});


function setupMessagesNavigation() {
  const nav = document.querySelector(".sidebar-nav");
  if (!nav || !WebStoreDevAPI.isAuthenticated()) return;
  let link = nav.querySelector('a[data-webstore-messages="dev"]') || Array.from(nav.querySelectorAll("a")).find(a => /messages\.html$/.test(a.getAttribute("href") || ""));
  if (!link) { link = document.createElement("a"); link.href = "messages.html"; link.textContent = "Messages"; nav.appendChild(link); }
  link.dataset.webstoreMessages = "dev";
  if (window.location.pathname.endsWith("/messages.html")) link.classList.add("active");
  let badge = link.querySelector(".message-unread-badge");
  if (!badge) { badge = document.createElement("span"); badge.className = "message-unread-badge"; badge.style.cssText = "display:none;float:right;min-width:18px;padding:1px 5px;border-radius:10px;background:#dc2626;color:#fff;font-size:12px;text-align:center"; link.appendChild(badge); }
  const refresh = async () => {
    try { const items = await WebStoreDevAPI.getMessages(); const count = items.filter(m => !m.read).length; badge.textContent = count > 99 ? "99+" : String(count); badge.style.display = count ? "inline-block" : "none"; } catch (_) {}
  };
  refresh(); window.setInterval(refresh, 30000);
}
