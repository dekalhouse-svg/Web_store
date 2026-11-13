/* WEB STORE — petite fenêtre modale obligatoire des conditions générales */
(() => {
  'use strict';
  const VERSION = '2026-11-13-v2';
  const KEY = 'webstore_terms_acceptance';
  const legalPage = /\/pages\/conditions\.html$/i.test(location.pathname);
  const accepted = () => {
    try { return JSON.parse(localStorage.getItem(KEY) || 'null')?.version === VERSION; }
    catch (_) { return false; }
  };
  if (legalPage || accepted()) return;

  const showGate = () => {
    if (document.getElementById('wsConsentGate')) return;
    const inPages = /\/pages\//i.test(location.pathname);
    const legalUrl = inPages ? 'conditions.html' : 'pages/conditions.html';
    const overlay = document.createElement('div');
    overlay.id = 'wsConsentGate';
    overlay.className = 'ws-consent-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'wsConsentTitle');
    overlay.innerHTML = `
      <section class="ws-consent-card">
        <p class="ws-consent-eyebrow">Bienvenue sur WEB STORE</p>
        <h2 id="wsConsentTitle">Conditions générales</h2>
        <p class="ws-consent-message">En cliquant sur « J’accepte », vous acceptez les conditions générales d’utilisation de WEB STORE, y compris leurs prochaines mises à jour dans les limites prévues par la loi.</p>
        <a class="ws-consent-link" href="${legalUrl}" target="_blank" rel="noopener">Voir les conditions</a>
        <button type="button" class="ws-consent-accept" id="wsConsentAccept">J’accepte</button>
      </section>`;
    document.body.append(overlay);
    document.documentElement.classList.add('ws-consent-locked');
    document.body.classList.add('ws-consent-locked');
    document.getElementById('wsConsentAccept').addEventListener('click', () => {
      try {
        localStorage.setItem(KEY, JSON.stringify({version: VERSION, accepted_at: new Date().toISOString()}));
        overlay.remove();
        document.documentElement.classList.remove('ws-consent-locked');
        document.body.classList.remove('ws-consent-locked');
      } catch (_) {
        alert('Le stockage local est désactivé. Autorisez-le dans votre navigateur pour continuer.');
      }
    });
    document.getElementById('wsConsentAccept').focus({preventScroll:true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showGate, {once:true});
  else showGate();
})();
