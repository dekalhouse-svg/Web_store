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
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      await WebStoreAdminAPI.logout();
    } catch (error) {
      // La copie locale est déjà effacée par logout(); la navigation reste possible.
    } finally {
      window.location.href = "/pages/login.html";
    }
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

  const swPath = window.location.pathname.includes("/pages/")
    ? "../service-worker.js"
    : "service-worker.js";

  // Vérifie auprès du serveur s'il existe une nouvelle version à chaque ouverture.
  navigator.serviceWorker.register(swPath, { updateViaCache: "none" })
    .then((registration) => {
      if (navigator.onLine) registration.update().catch(() => {});

      // Si une nouvelle version est installée alors qu'une ancienne contrôle déjà
      // la page, recharge une seule fois pour afficher les fichiers à jour.
      registration.addEventListener("updatefound", () => {
        const installing = registration.installing;
        if (!installing) return;
        const hadController = Boolean(navigator.serviceWorker.controller);
        const updateToken = String(Date.now());
        installing.addEventListener("statechange", () => {
          if (installing.state === "activated" && hadController) {
            const key = "webstore-admin-sw-reload";
            if (sessionStorage.getItem(key) !== updateToken) {
              sessionStorage.setItem(key, updateToken);
              window.location.reload();
            }
          }
        });
      });
    })
    .catch(() => {});
}


function setupMessagesNavigation() {
  const nav = document.querySelector(".sidebar-nav");
  if (!nav || !WebStoreAdminAPI.isAuthenticated()) return;

  // Réutilise les liens déjà présents dans les pages et supprime les doublons.
  // Avant, le lien statique du tableau de bord n'avait pas de data-attribute :
  // le script en ajoutait donc un deuxième au chargement.
  const getOrCreateLink = (dataKey, href, label) => {
    const matches = [...nav.querySelectorAll("a")].filter((item) => {
      const target = (item.getAttribute("href") || "").split("?")[0].split("#")[0];
      return item.dataset[dataKey] === "admin" || target.endsWith("/" + href) || target === href;
    });
    const link = matches.shift() || document.createElement("a");
    matches.forEach((duplicate) => duplicate.remove());
    link.href = href;
    link.dataset[dataKey] = "admin";
    if (!link.textContent.trim()) link.textContent = label;
    const current = window.location.pathname.split("/").pop();
    link.classList.toggle("active", current === href);
    if (!link.isConnected) nav.appendChild(link);
    return link;
  };

  const link = getOrCreateLink("webstoreMessages", "messages.html", "Messages");
  getOrCreateLink("webstoreCampaigns", "campaigns.html", "Publicités");

  let badge = link.querySelector(".message-unread-badge");
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "message-unread-badge";
    badge.setAttribute("aria-label", "Messages non lus");
    badge.style.cssText = "display:none;float:right;min-width:18px;padding:1px 5px;border-radius:10px;background:#dc2626;color:#fff;font-size:12px;text-align:center";
    link.appendChild(badge);
  }

  const refresh = async () => {
    try {
      const items = await WebStoreAdminAPI.getMessages("inbox");
      const count = items.filter((message) => !message.read).length;
      badge.textContent = count > 99 ? "99+" : String(count);
      badge.style.display = count ? "inline-block" : "none";
    } catch (_) {}
  };
  refresh();
  window.setInterval(refresh, 30000);
}
