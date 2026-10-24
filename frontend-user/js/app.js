/* ================= ÉTAT ================= */

let allProjects = [];
let activeCategory = "all";
let deferredInstallPrompt = null;

/* ================= INITIALISATION ================= */

document.addEventListener("DOMContentLoaded", () => {
  registerServiceWorker();
  WebStoreAPI.trackVisitor().catch(() => {});
  loadCategories();
  loadProjects();
  bindSearch();
  bindMenu();
  bindOfflineBanner();
  bindInstallPrompt();
});

/* ================= SERVICE WORKER ================= */

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;

  // Si un nouveau Service Worker prend le contrôle, recharge une seule fois
  // pour afficher la version fraîchement déployée.
  let reloadedForUpdate = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloadedForUpdate) return;
    reloadedForUpdate = true;
    window.location.reload();
  });

  navigator.serviceWorker.register("/service-worker.js", { updateViaCache: "none" })
    .then((registration) => {
      // Force une vérification de mise à jour à chaque ouverture.
      registration.update().catch(() => {});
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
          registration.update().catch(() => {});
        }
      });
    })
    .catch(() => {
      // L'app reste utilisable en ligne même si l'enregistrement échoue.
    });
}

/* ================= MENU MOBILE ================= */

function bindMenu() {
  const btn = document.getElementById("menuBtn");
  const menu = document.getElementById("menu");
  if (!btn || !menu) return;
  btn.addEventListener("click", () => menu.classList.toggle("active"));
}

/* ================= CATÉGORIES ================= */

async function loadCategories() {
  const container = document.getElementById("categoryList");
  if (!container) return;

  try {
    const categories = await WebStoreAPI.getCategories();
    categories.forEach((category) => {
      const btn = document.createElement("button");
      btn.className = "category";
      btn.textContent = category.name;
      btn.dataset.slug = category.slug;
      btn.addEventListener("click", () => selectCategory(btn));
      container.appendChild(btn);
    });
  } catch (err) {
    // Pas de backend disponible pour le moment : on garde uniquement "Tous".
    console.warn("Catégories indisponibles :", err.message);
  }
}

function selectCategory(button) {
  document
    .querySelectorAll(".category")
    .forEach((btn) => btn.classList.remove("active"));
  button.classList.add("active");
  activeCategory = button.dataset.slug || "all";
  renderProjects();
}

/* ================= PROJETS ================= */

async function loadProjects() {
  const list = document.getElementById("projectList");
  const empty = document.getElementById("empty");
  if (!list) return;

  try {
    allProjects = await WebStoreAPI.getProjects();
    renderProjects();
  } catch (err) {
    console.warn("Projets indisponibles :", err.message);
    allProjects = [];
    list.innerHTML = "";
    if (empty) {
      empty.style.display = "block";
      empty.textContent =
        "Impossible de charger les projets pour le moment. Réessayez plus tard.";
    }
  }
}

function renderProjects() {
  const list = document.getElementById("projectList");
  const featuredSection = document.getElementById("featuredSection");
  const featuredList = document.getElementById("featuredList");
  const empty = document.getElementById("empty");
  const searchValue = (document.getElementById("search")?.value || "")
    .toLowerCase()
    .trim();

  const featured = allProjects.filter((project) => project.featured);
  if (featuredSection && featuredList) {
    featuredSection.hidden = featured.length === 0;
   featuredList.replaceChildren(...featured.map(buildProjectCard));
  }

  const filtered = allProjects.filter((project) => {
    const matchesCategory =
      activeCategory === "all" || project.category_slug === activeCategory;
    const matchesSearch = project.name.toLowerCase().includes(searchValue);
    return matchesCategory && matchesSearch;
  });

  list.innerHTML = "";

  if (filtered.length === 0) {
    if (empty) {
      empty.style.display = "block";
      empty.textContent = "Aucun projet trouvé.";
    }
    return;
  }

  if (empty) empty.style.display = "none";

  filtered.forEach((project) => list.appendChild(buildProjectCard(project)));
}

function buildProjectCard(project) {
  const article = document.createElement("article");
  article.className = "project";

  article.innerHTML = `
    <div class="project-icon">${escapeHtml(initials(project.name))}</div>
    <div class="project-info">
      <h3>${escapeHtml(project.name)}</h3>
      <p>${escapeHtml(project.short_description || "")}</p>
      <span class="badge ${project.type === "PWA" ? "pwa" : "web"}">
        ${project.type === "PWA" ? "PWA" : "WEB"}
      </span>
    </div>
    <button class="open-button">Ouvrir</button>
  `;

  applyProjectIcon(article.querySelector(".project-icon"), project);

  article
    .querySelector(".open-button")
    .addEventListener("click", () => openProject(project.slug));

  return article;
}

// Affiche l'icône définie par le développeur à la publication (icon_data).
// Les initiales restent affichées uniquement s'il n'y a pas d'icône
// (ou si l'image ne peut pas être affichée).
function applyProjectIcon(box, project) {
  const iconPath = project.icon_url;
  if (!box || typeof iconPath !== "string" || !iconPath) return;

  const img = document.createElement("img");
  img.className = "project-icon-image";
  img.alt = "";
  img.loading = "lazy";
  img.decoding = "async";
  img.addEventListener("error", () => {
    box.textContent = initials(project.name);
  }, { once: true });
  img.src = WebStoreAPI.getAssetUrl(iconPath);
  box.replaceChildren(img);
}

function openProject(slug) {
  window.location.href = `pages/project.html?slug=${encodeURIComponent(slug)}`;
}

/* ================= RECHERCHE ================= */

function bindSearch() {
  const input = document.getElementById("search");
  if (!input) return;
  input.addEventListener("input", renderProjects);
}

/* ================= UTILS ================= */

function initials(name) {
  return name
    .split(" ")
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

/* ================= INSTALLATION / PARTAGE ================= */

function bindInstallPrompt() {
  const btn = document.getElementById("appActionBtn");
  if (!btn) return;

  const isInstalled = () =>
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true;

  const updateButton = () => {
    btn.hidden = false;
    btn.textContent = isInstalled() ? "Partager" : "Installer";
  };

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt = event;
    updateButton();
  });

  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    updateButton();
  });

  btn.addEventListener("click", async () => {
    if (isInstalled()) {
      const shareData = {
        title: document.title || "WEB STORE",
        text: "Découvre WEB STORE",
        url: window.location.href
      };
      if (navigator.share) {
        try { await navigator.share(shareData); } catch (_) {}
      } else if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(window.location.href);
          btn.textContent = "Lien copié";
          setTimeout(updateButton, 1800);
        } catch (_) {
          window.prompt("Copiez le lien de l’application :", window.location.href);
        }
      } else {
        window.prompt("Copiez le lien de l’application :", window.location.href);
      }
      return;
    }

    if (deferredInstallPrompt) {
      deferredInstallPrompt.prompt();
      await deferredInstallPrompt.userChoice;
      deferredInstallPrompt = null;
      updateButton();
    } else {
      alert("Pour installer WEB STORE, ouvrez le menu du navigateur puis choisissez « Installer l’application » ou « Ajouter à l’écran d’accueil ».");
    }
  });

  updateButton();
  window.matchMedia("(display-mode: standalone)").addEventListener?.("change", updateButton);
}

/* ================= BANNIÈRE HORS LIGNE ================= */

function bindOfflineBanner() {
  const banner = document.getElementById("offlineBanner");
  if (!banner) return;

  const update = () => {
    banner.hidden = navigator.onLine;
  };

  window.addEventListener("online", update);
  window.addEventListener("offline", update);
  update();
}
