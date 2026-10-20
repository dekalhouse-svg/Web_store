window.WEBSTORE_API_BASE_URL = "https://web-store-back.onrender.com/api";

// Bouton unique : installer l'espace développeur, puis le partager une fois installé.
(function () {
  "use strict";

  var deferredInstallPrompt = null;
  var button = null;
  var installEventAvailable = false;

  function isInstalled() {
    return window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: minimal-ui)").matches ||
      window.navigator.standalone === true;
  }

  function updateButton() {
    if (!button) return;
    var installed = isInstalled();
    button.textContent = installed ? "Partager l’application" : "Installer l’application";
    button.setAttribute("aria-label", button.textContent);
    button.title = installed
      ? "Partager WEB STORE Espace Développeur"
      : "Installer WEB STORE Espace Développeur";
  }

  function showNotice(message) {
    var notice = document.getElementById("webstoreInstallNotice");
    if (!notice) {
      notice = document.createElement("div");
      notice.id = "webstoreInstallNotice";
      notice.setAttribute("role", "status");
      notice.style.cssText = "position:fixed;left:16px;right:16px;bottom:76px;z-index:100000;" +
        "max-width:480px;margin:0 auto;padding:12px 14px;border-radius:10px;" +
        "background:#12291B;color:#fff;font:14px/1.4 Arial,sans-serif;box-shadow:0 4px 18px #0003";
      document.body.appendChild(notice);
    }
    notice.textContent = message;
    notice.hidden = false;
    clearTimeout(notice._hideTimer);
    notice._hideTimer = setTimeout(function () { notice.hidden = true; }, 5000);
  }

  async function handleButtonClick() {
    if (isInstalled()) {
      var shareData = {
        title: "WEB STORE - Espace Développeur",
        text: "Gérez et partagez vos projets sur WEB STORE.",
        url: window.location.origin + "/"
      };
      if (navigator.share) {
        try {
          await navigator.share(shareData);
        } catch (err) {
          if (err && err.name !== "AbortError") {
            showNotice("Le partage n’a pas pu être ouvert sur cet appareil.");
          }
        }
      } else {
        try {
          await navigator.clipboard.writeText(shareData.url);
          showNotice("Lien de l’application copié : " + shareData.url);
        } catch (err) {
          showNotice("Copiez ce lien pour partager l’application : " + shareData.url);
        }
      }
      return;
    }

    if (deferredInstallPrompt) {
      deferredInstallPrompt.prompt();
      try {
        await deferredInstallPrompt.userChoice;
      } catch (err) {}
      deferredInstallPrompt = null;
      updateButton();
      return;
    }

    if (installEventAvailable) {
      showNotice("L’installation a déjà été proposée. Consultez le menu du navigateur si nécessaire.");
    } else {
      showNotice("Si l’installation n’est pas proposée automatiquement, ouvrez le menu du navigateur puis choisissez « Installer l’application » ou « Ajouter à l’écran d’accueil ».");
    }
  }

  function addButton() {
    if (button || !document.body) return;
    button = document.createElement("button");
    button.id = "webstoreInstallShareButton";
    button.type = "button";
    button.textContent = "Installer l’application";
    button.addEventListener("click", handleButtonClick);
    button.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:99999;" +
      "border:0;border-radius:999px;padding:12px 16px;background:#16A34A;color:#fff;" +
      "font:600 14px/1.2 Arial,sans-serif;box-shadow:0 4px 16px #0003;cursor:pointer;" +
      "max-width:calc(100vw - 32px)";
    document.body.appendChild(button);
    updateButton();
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredInstallPrompt = event;
    installEventAvailable = true;
    updateButton();
  });

  window.addEventListener("appinstalled", function () {
    deferredInstallPrompt = null;
    updateButton();
    showNotice("WEB STORE Espace Développeur a été installé.");
  });

  window.addEventListener("DOMContentLoaded", addButton);
  if (document.readyState !== "loading") addButton();

  // Le mode d’affichage peut changer après l’installation ou au retour dans l’application.
  window.addEventListener("pageshow", updateButton);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) updateButton();
  });
  try {
    window.matchMedia("(display-mode: standalone)").addEventListener("change", updateButton);
  } catch (err) {}
})();

// Mises à jour automatiques : charge js/updater.js sur chaque page.
(function () {
  if (!("serviceWorker" in navigator) || !document.currentScript) return;
  var s = document.createElement("script");
  s.src = new URL("updater.js", document.currentScript.src).href;
  s.async = true;
  document.head.appendChild(s);
})();
