
window.WEBSTORE_API_BASE_URL = "https://web-store-back.onrender.com/api";

// Mises à jour automatiques : charge js/updater.js sur chaque page
// (voir service-worker.js pour publier une nouvelle version).
(function () {
  if (!("serviceWorker" in navigator) || !document.currentScript) return;
  var s = document.createElement("script");
  s.src = new URL("updater.js", document.currentScript.src).href;
  s.async = true;
  document.head.appendChild(s);
})();
