/* WEB STORE — acceptation obligatoire des conditions avant accès */
(() => {
  'use strict';
  const VERSION = '2026-11-13-v1';
  const KEY = 'webstore_terms_acceptance';
  const legalPage = /\/pages\/conditions\.html$/i.test(location.pathname);
  const accepted = () => {
    try { return JSON.parse(localStorage.getItem(KEY) || 'null')?.version === VERSION; }
    catch (_) { return false; }
  };
  if (legalPage || accepted()) return;

  const showGate = () => {
    if (document.getElementById('wsConsentGate')) return;
    const overlay = document.createElement('div');
    overlay.id = 'wsConsentGate';
    overlay.className = 'ws-consent-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'wsConsentTitle');
    overlay.innerHTML = `
      <section class="ws-consent-card">
        <div class="ws-consent-brand"><span class="ws-consent-mark">W</span><span>WEB STORE</span></div>
        <p class="ws-consent-eyebrow">Bienvenue sur WEB STORE</p>
        <h1 id="wsConsentTitle">Avant de découvrir le Web</h1>
        <p class="ws-consent-intro">Veuillez lire le document unique qui regroupe les conditions d’utilisation, la confidentialité et les cookies. L’accès au catalogue est conditionné par l’acceptation des conditions générales.</p>
        <div class="ws-consent-links">
          <a href="${location.pathname.includes('/pages/') ? '' : 'pages/'}conditions.html">Conditions générales <span>Lire le document complet →</span></a>
        </div>
        <p class="ws-consent-note">En acceptant, vous acceptez les conditions générales d’utilisation actuelles et leurs prochaines mises à jour. Les cookies facultatifs et la personnalisation publicitaire, lorsqu’ils sont soumis à consentement, feront l’objet d’un choix séparé.</p>
        <button type="button" class="ws-consent-accept" id="wsConsentAccept">J’accepte les conditions générales et je continue</button>
        <p class="ws-consent-foot">En cas de refus, vous ne pourrez pas accéder au catalogue. Vous pouvez quitter cette page.</p>
        <p class="ws-consent-contact">Une question ? <a href="mailto:dekalhouse@gmail.com">dekalhouse@gmail.com</a></p>
      </section>`;
    document.body.append(overlay);
    document.documentElement.classList.add('ws-consent-locked');
    document.getElementById('wsConsentAccept').addEventListener('click', () => {
      try {
        localStorage.setItem(KEY, JSON.stringify({version: VERSION, accepted_at: new Date().toISOString()}));
        location.reload();
      } catch (_) {
        alert('Le stockage local est désactivé. Autorisez-le dans votre navigateur pour continuer.');
      }
    });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showGate, {once:true});
  else showGate();
})();
