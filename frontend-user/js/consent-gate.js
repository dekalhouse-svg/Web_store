/* WEB STORE — fenêtre obligatoire des conditions générales */
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
        <header class="ws-consent-header">
          <div class="ws-consent-brand"><span class="ws-consent-mark">WS</span><span>WEB STORE</span></div>
          <span class="ws-consent-secure">Document officiel</span>
        </header>
        <div class="ws-consent-heading">
          <p class="ws-consent-eyebrow">Bienvenue sur WEB STORE</p>
          <h1 id="wsConsentTitle">Conditions générales</h1>
          <p>Veuillez prendre connaissance du document complet avant de continuer.</p>
        </div>
        <iframe class="ws-consent-document" src="${legalUrl}" title="Conditions générales, confidentialité et cookies"></iframe>
        <footer class="ws-consent-footer">
          <p class="ws-consent-acceptance">En acceptant, vous acceptez les conditions générales d’utilisation actuelles et leurs prochaines mises à jour, dans les limites prévues par la loi. Les consentements facultatifs, notamment pour les cookies non essentiels et la publicité personnalisée, restent séparés.</p>
          <button type="button" class="ws-consent-accept" id="wsConsentAccept">J’accepte les conditions générales et je continue</button>
          <p class="ws-consent-refusal">En cas de refus, l’accès au catalogue reste bloqué. Vous pouvez fermer cette page.</p>
          <p class="ws-consent-contact">Une question ? <a href="mailto:dekalhouse@gmail.com">dekalhouse@gmail.com</a></p>
        </footer>
      </section>`;
    document.body.append(overlay);
    document.documentElement.classList.add('ws-consent-locked');
    document.body.classList.add('ws-consent-locked');
    const accept = document.getElementById('wsConsentAccept');
    accept.addEventListener('click', () => {
      try {
        localStorage.setItem(KEY, JSON.stringify({version: VERSION, accepted_at: new Date().toISOString()}));
        location.reload();
      } catch (_) {
        alert('Le stockage local est désactivé. Autorisez-le dans votre navigateur pour continuer.');
      }
    });
    accept.focus({preventScroll:true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showGate, {once:true});
  else showGate();
})();
