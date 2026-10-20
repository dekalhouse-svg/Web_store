/**
 * Mises à jour automatiques — WEB STORE Dev
 *
 * - enregistre le service worker et lui demande « y a-t-il du nouveau ? »
 *   à chaque ouverture, au retour sur l'app, au retour du réseau et toutes les 15 min ;
 * - quand une nouvelle version est installée, recharge la page toute seule ;
 * - si le développeur est en train de remplir un formulaire, il ne perd rien :
 *   un bandeau « Mettre à jour » apparaît à la place.
 *
 * Chargé automatiquement par js/config.js (donc sur toutes les pages).
 */
(function () {
  "use strict";
  if (!("serviceWorker" in navigator)) return;

  var CHECK_EVERY_MS = 15 * 60 * 1000;
  var RELOAD_GUARD_KEY = "webstore_dev_last_update_reload";

  var script = document.currentScript;
  var swUrl = script && script.src
    ? new URL("../service-worker.js", script.src).href
    : "/service-worker.js";

  var registration = null;
  var controlled = Boolean(navigator.serviceWorker.controller);
  var hasUnsavedInput = false;

  // Repère un formulaire en cours de saisie pour ne pas recharger la page dessus
  document.addEventListener(
    "input",
    function (e) {
      var t = e.target;
      if (t && t.closest && t.closest("form")) hasUnsavedInput = true;
    },
    true
  );

  function checkForUpdate() {
    if (!registration) return;
    registration.update().catch(function () {});
  }

  function recentlyReloaded() {
    try {
      var last = Number(sessionStorage.getItem(RELOAD_GUARD_KEY) || 0);
      return Date.now() - last < 10000; // garde-fou anti-boucle
    } catch (e) {
      return false;
    }
  }

  function reloadNow() {
    try {
      sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()));
    } catch (e) {}
    window.location.reload();
  }

  function showBar(text, buttonLabel, onClick) {
    if (document.getElementById("wsUpdateBar")) return;
    var bar = document.createElement("div");
    bar.id = "wsUpdateBar";
    bar.setAttribute("role", "status");
    bar.style.cssText =
      "position:fixed;left:12px;right:12px;bottom:12px;z-index:99999;display:flex;" +
      "align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;" +
      "background:#12291B;color:#fff;border-radius:10px;font:14px -apple-system,'Segoe UI',Roboto,Arial,sans-serif;" +
      "box-shadow:0 6px 24px rgba(0,0,0,.25);max-width:520px;margin:0 auto;";
    var span = document.createElement("span");
    span.textContent = text;
    bar.appendChild(span);
    if (buttonLabel) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = buttonLabel;
      btn.style.cssText =
        "border:0;border-radius:8px;padding:8px 14px;background:#16A34A;color:#fff;font-weight:600;cursor:pointer;";
      btn.addEventListener("click", onClick);
      bar.appendChild(btn);
    }
    document.body.appendChild(bar);
  }

  function applyUpdate() {
    if (recentlyReloaded()) return;
    if (hasUnsavedInput) {
      showBar("Une nouvelle version est prête.", "Mettre à jour", reloadNow);
      return;
    }
    showBar("Mise à jour installée, rechargement…");
    setTimeout(reloadNow, 600);
  }

  // Un nouveau service worker vient de prendre la main
  navigator.serviceWorker.addEventListener("controllerchange", function () {
    if (!controlled) {
      // Toute première installation : rien à recharger
      controlled = true;
      return;
    }
    applyUpdate();
  });

  navigator.serviceWorker
    .register(swUrl, { updateViaCache: "none" })
    .then(function (reg) {
      registration = reg;
      checkForUpdate(); // vérification à chaque ouverture
    })
    .catch(function () {});

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") checkForUpdate();
  });
  window.addEventListener("online", checkForUpdate);
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) checkForUpdate();
  });
  setInterval(checkForUpdate, CHECK_EVERY_MS);

  window.WebStoreUpdater = { checkNow: checkForUpdate };
})();
