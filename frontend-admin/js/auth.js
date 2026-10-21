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
  setupAdminNavigation();
  registerServiceWorker();
});

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  const swPath = window.location.pathname.includes("/pages/") ? "../service-worker.js" : "service-worker.js";
  navigator.serviceWorker.register(swPath).catch(() => {});
}

/* Garantit que Messages et Profil sont disponibles sur toutes les pages admin,
   sans créer de doublons lorsque les liens existent déjà. */
function setupAdminNavigation() {
  const nav = document.querySelector(".sidebar-nav");
  if (!nav || !WebStoreAdminAPI.isAuthenticated()) return;
  const current = window.location.pathname.split("/").pop() || "dashboard.html";
  const ensureLink = (filename, label, dataKey) => {
    let link = nav.querySelector(`a[data-webstore-${dataKey}]`) ||
      [...nav.querySelectorAll("a[href]")].find(a => a.getAttribute("href").split("/").pop() === filename);
    if (!link) {
      link = document.createElement("a");
      link.href = filename;
      nav.appendChild(link);
    }
    link.dataset[`webstore${dataKey.charAt(0).toUpperCase()}${dataKey.slice(1)}`] = "admin";
    // Uniformise le libellé sans supprimer le badge éventuel du lien Messages.
    for (const child of [...link.childNodes]) { if (child.nodeType === Node.TEXT_NODE) child.remove(); }
    link.insertBefore(document.createTextNode(label), link.firstChild);
    if (current === filename) link.classList.add("active");
    else link.classList.remove("active");
    return link;
  };
  const messagesLink = ensureLink("messages.html", "Messages", "messages");
  ensureLink("profile.html", "Profil", "profile");
  let badge = messagesLink.querySelector(".message-unread-badge");
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "message-unread-badge";
    badge.style.cssText = "display:none;float:right;min-width:18px;padding:1px 5px;border-radius:10px;background:#dc2626;color:#fff;font-size:12px;text-align:center";
    messagesLink.appendChild(badge);
  }
  const refresh = async () => {
    try {
      const items = await WebStoreAdminAPI.getMessages("inbox");
      if (!Array.isArray(items)) return;
      const count = items.filter(m => !m.read).length;
      badge.textContent = count > 99 ? "99+" : String(count);
      badge.style.display = count ? "inline-block" : "none";
      badge.setAttribute("aria-label", `${count} message(s) non lu(s)`);
    } catch (_) { /* Le menu reste utilisable si l'API est temporairement indisponible. */ }
  };
  refresh();
  window.setInterval(refresh, 30000);
}
