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
  bindAppInstallShare();
  registerServiceWorker();
});

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  const swPath = window.location.pathname.includes("/pages/") ? "../service-worker.js" : "service-worker.js";
  navigator.serviceWorker.register(swPath).catch(() => {});
}

/* Bouton global d'installation / partage pour l'espace développeur */
let devInstallPrompt = null;

function bindAppInstallShare() {
  const topbar = document.querySelector(".topbar");
  if (!topbar) return;

  const button = document.createElement("button");
  button.type = "button";
  button.id = "appActionBtn";
  button.style.cssText = "border:0;border-radius:8px;padding:9px 12px;background:#16A34A;color:#fff;font-weight:600;cursor:pointer;";
  topbar.appendChild(button);

  const isInstalled = () =>
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true;

  const updateButton = () => {
    button.textContent = isInstalled() ? "Partager" : "Installer";
  };

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    devInstallPrompt = event;
    updateButton();
  });

  window.addEventListener("appinstalled", () => {
    devInstallPrompt = null;
    updateButton();
  });

  button.addEventListener("click", async () => {
    const appUrl = new URL("../index.html", window.location.href).href;
    if (isInstalled()) {
      if (navigator.share) {
        try {
          await navigator.share({ title: "WEB STORE — Espace Développeur", text: "Découvre WEB STORE", url: appUrl });
        } catch (_) {}
      } else if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(appUrl);
          button.textContent = "Lien copié";
          setTimeout(updateButton, 1800);
        } catch (_) {
          window.prompt("Copiez le lien de WEB STORE :", appUrl);
        }
      } else {
        window.prompt("Copiez le lien de WEB STORE :", appUrl);
      }
      return;
    }

    if (devInstallPrompt) {
      devInstallPrompt.prompt();
      await devInstallPrompt.userChoice;
      devInstallPrompt = null;
      updateButton();
    } else {
      alert("Pour installer WEB STORE, ouvrez le menu du navigateur puis choisissez « Installer l’application » ou « Ajouter à l’écran d’accueil ».");
    }
  });

  updateButton();
  window.matchMedia("(display-mode: standalone)").addEventListener?.("change", updateButton);
}
