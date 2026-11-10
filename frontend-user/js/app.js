/* WEB STORE — catalogue public */
let allProjects = [];
let categories = [];
let favoriteSlugs = new Set();
let activeFilter = "all";
let favoritesOnly = false;
let deferredInstallPrompt = null;

const ICONS = {
  search: '<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.5 4.5"/>',
  heart: '<path d="M20.8 8.8c0 5.2-8.8 10.1-8.8 10.1S3.2 14 3.2 8.8A4.7 4.7 0 0 1 12 6.2a4.7 4.7 0 0 1 8.8 2.6Z"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  chevron: '<path d="m9 18 6-6-6-6"/>',
  sparkles: '<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z"/><path d="m19 16 .9 2.1L22 19l-2.1.9L19 22l-.9-2.1L16 19l2.1-.9L19 16Z"/>',
  code: '<path d="m8 8-4 4 4 4m8-8 4 4-4 4m-2-11-4 14"/>',
  briefcase: '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18m-11 0v2h4v-2"/>',
  book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 0 4 22V5.5Z"/><path d="M4 17a2.5 2.5 0 0 1 2.5-2.5H20"/>',
  play: '<path d="m8 5 11 7-11 7V5Z"/>',
  shield: '<path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z"/><path d="m9 12 2 2 4-4"/>',
  tool: '<path d="M14.7 6.3a5 5 0 0 0-6.4 6.4L3 18l3 3 5.3-5.3a5 5 0 0 0 6.4-6.4L14 12l-2-2 2.7-3.7Z"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/>'
};

function svgIcon(name, className = "") {
  return `<svg class="${className}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[name] || ICONS.globe}</svg>`;
}

document.addEventListener("DOMContentLoaded", initStore);

async function initStore() {
  registerServiceWorker();
  bindInstallPrompt();
  bindOfflineBanner();
  bindSearch();
  bindMenu();
  bindFilters();

  const requestedCategory = new URLSearchParams(location.search).get("category");
  try {
    await WebStoreAPI.trackVisitor();
  } catch (_) {}

  const results = await Promise.allSettled([
    WebStoreAPI.getCategories(),
    WebStoreAPI.getProjects()
  ]);

  if (results[0].status === "fulfilled") {
    categories = results[0].value || [];
    renderCategories();
  }
  if (results[1].status === "fulfilled") {
    allProjects = results[1].value || [];
    await loadFavoriteStates();
    if (requestedCategory) {
      activeFilter = `category:${requestedCategory}`;
      const selected = [...document.querySelectorAll(".catalog-tab")].find(
        (tab) => tab.dataset.category === requestedCategory
      );
      if (selected) setActiveTab(selected);
    }
    renderProjects();
  } else {
    showProjectError();
  }
  window.dispatchEvent(new Event("webstore:content-ready"));
}

async function loadFavoriteStates() {
  if (!allProjects.length) return;
  const states = await Promise.allSettled(
    allProjects.map((project) => WebStoreAPI.getFavorite(project.slug))
  );
  states.forEach((result, index) => {
    if (result.status === "fulfilled" && result.value?.is_favorite) {
      favoriteSlugs.add(allProjects[index].slug);
      allProjects[index].favorites_count = result.value.favorites_count ?? allProjects[index].favorites_count;
    }
  });
}

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloaded) return;
    reloaded = true;
    location.reload();
  });
  navigator.serviceWorker.register("/service-worker.js", { updateViaCache: "none" })
    .then((registration) => {
      registration.update().catch(() => {});
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") registration.update().catch(() => {});
      });
    }).catch(() => {});
}

function bindMenu() {
  const button = document.getElementById("menuBtn");
  const menu = document.getElementById("menu");
  if (!button || !menu) return;
  button.addEventListener("click", () => {
    const opened = menu.classList.toggle("is-open");
    button.setAttribute("aria-expanded", String(opened));
  });
}

function bindSearch() {
  const input = document.getElementById("search");
  const clear = document.getElementById("clearSearch");
  if (!input) return;
  input.addEventListener("input", () => {
    if (clear) clear.hidden = !input.value;
    favoritesOnly = false;
    renderProjects();
  });
  clear?.addEventListener("click", () => {
    input.value = "";
    clear.hidden = true;
    input.focus();
    renderProjects();
  });
}

function bindFilters() {
  document.querySelectorAll(".catalog-tab[data-filter]").forEach((tab) => {
    tab.addEventListener("click", () => {
      favoritesOnly = false;
      activeFilter = tab.dataset.filter;
      setActiveTab(tab);
      renderProjects();
    });
  });
  document.getElementById("favoritesNav")?.addEventListener("click", () => {
    favoritesOnly = !favoritesOnly;
    document.getElementById("favoritesNav").classList.toggle("is-active", favoritesOnly);
    renderProjects();
    document.getElementById("popularSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.getElementById("showAllProjects")?.addEventListener("click", () => {
    favoritesOnly = false;
    activeFilter = "all";
    const allTab = document.querySelector('.catalog-tab[data-filter="all"]');
    if (allTab) setActiveTab(allTab);
    renderProjects();
  });
}

function setActiveTab(selected) {
  document.querySelectorAll(".catalog-tab[data-filter]").forEach((tab) => {
    tab.classList.toggle("is-active", tab === selected);
  });
}

function renderCategories() {
  const shortcuts = document.getElementById("categoryShortcuts");
  if (!shortcuts) return;
  const iconByName = (name) => {
    const value = String(name || "").toLowerCase();
    if (value.includes("techn") || value.includes("dévelop") || value.includes("cyber")) return "code";
    if (value.includes("product") || value.includes("outil")) return "tool";
    if (value.includes("éduc")) return "book";
    if (value.includes("divert")) return "play";
    if (value.includes("business")) return "briefcase";
    return "layers";
  };
  shortcuts.replaceChildren();
  categories.slice(0, 4).forEach((category) => {
    const link = document.createElement("a");
    link.className = "category-card";
    link.href = `pages/categories.html?selected=${encodeURIComponent(category.slug)}`;
    link.innerHTML = `<span class="category-icon">${svgIcon(iconByName(category.name))}</span><span>${escapeHtml(category.name)}</span>`;
    shortcuts.appendChild(link);
  });
}

function filteredProjects() {
  const search = (document.getElementById("search")?.value || "").trim().toLowerCase();
  return allProjects.filter((project) => {
    const searchable = [
      project.name, project.short_description, project.description,
      project.developer_name, project.category,
      ...(Array.isArray(project.tags) ? project.tags : [])
    ].filter(Boolean).join(" ").toLowerCase();
    const matchesSearch = searchable.includes(search);
    const matchesType = activeFilter === "all" ||
      (activeFilter === "web" && project.type !== "PWA") ||
      (activeFilter === "pwa" && project.type === "PWA") ||
      activeFilter.startsWith("category:");
    const matchesCategory = !activeFilter.startsWith("category:") ||
      project.category_slug === activeFilter.slice(9);
    const matchesFavorite = !favoritesOnly || favoriteSlugs.has(project.slug);
    return matchesSearch && matchesType && matchesCategory && matchesFavorite;
  });
}

function renderProjects() {
  const filtered = filteredProjects();
  const search = (document.getElementById("search")?.value || "").trim();
  const featuredSection = document.getElementById("featuredSection");
  const featuredList = document.getElementById("featuredList");
  const popularList = document.getElementById("projectList");
  const recentList = document.getElementById("recentList");
  const heading = document.getElementById("projectHeading");
  const empty = document.getElementById("empty");
  const recentSection = document.getElementById("recentSection");
  if (!popularList) return;

  const defaultView = activeFilter === "all" && !search && !favoritesOnly;
  const featured = defaultView ? filtered.find((project) => project.featured) : null;
  featuredSection.hidden = !featured;
  featuredList.replaceChildren();
  if (featured) featuredList.appendChild(buildFeaturedCard(featured));

  let popular = filtered.filter((project) => project !== featured);
  popular.sort((a, b) => Number(b.favorites_count || 0) - Number(a.favorites_count || 0));
  const recent = [...filtered].sort((a, b) => {
    const dateA = new Date(a.created_at || 0).getTime() || 0;
    const dateB = new Date(b.created_at || 0).getTime() || 0;
    return dateB - dateA;
  }).slice(0, 4);

  if (heading) heading.textContent = favoritesOnly ? "Mes favoris" :
    activeFilter === "web" ? "Sites web" :
    activeFilter === "pwa" ? "Applications PWA" :
    activeFilter.startsWith("category:") ? "Projets de cette catégorie" :
    search ? "Résultats de recherche" : "Populaires";

  popularList.replaceChildren();
  popular.forEach((project) => popularList.appendChild(buildProjectRow(project)));
  empty.hidden = popular.length > 0 || !!featured;
  if (empty && popular.length === 0 && !featured) {
    empty.textContent = favoritesOnly ? "Vous n'avez pas encore ajouté de projet à vos favoris." : "Aucun projet trouvé.";
  }

  recentList.replaceChildren();
  const showRecent = defaultView && recent.length > 0;
  recentSection.hidden = !showRecent;
  recent.forEach((project) => recentList.appendChild(buildProjectRow(project)));
}

function buildFeaturedCard(project) {
  const article = document.createElement("article");
  article.className = "featured-card";
  article.innerHTML = `
    <div class="featured-top">
      <span class="featured-label">${svgIcon("sparkles")} PROJET EN VEDETTE</span>
      ${favoriteButtonMarkup(project)}
    </div>
    <div class="featured-main">
      <div class="project-icon">${escapeHtml(initials(project.name))}</div>
      <div class="project-summary">
        <h3 class="project-name">${escapeHtml(project.name)}</h3>
        <p class="project-meta">par ${escapeHtml(project.developer_name || "Développeur")}</p>
        <p class="project-meta">${project.type === "PWA" ? "Application PWA" : "Site web"} · ${escapeHtml(project.category || "Autre")}</p>
        <p class="project-meta favorite-count">${svgIcon("heart")} ${Number(project.favorites_count || 0)} favoris</p>
        <p class="featured-description">${escapeHtml(project.short_description || project.description || "Découvrez ce projet sur WEB STORE.")}</p>
      </div>
    </div>
    <a class="featured-open" href="pages/project.html?slug=${encodeURIComponent(project.slug)}">Découvrir le projet</a>`;
  applyProjectIcon(article.querySelector(".project-icon"), project);
  bindFavoriteButton(article.querySelector(".project-favorite"), project, article);
  return article;
}

function buildProjectRow(project) {
  const article = document.createElement("article");
  article.className = "project-row";
  article.innerHTML = `
    <div class="project-icon">${escapeHtml(initials(project.name))}</div>
    <div class="row-details">
      <h3 class="project-name">${escapeHtml(project.name)}</h3>
      <p class="project-meta">${escapeHtml(project.developer_name || "Développeur")}</p>
      <p class="project-meta">${escapeHtml(project.category || "Autre")} · ${project.type === "PWA" ? "PWA" : "Site web"}</p>
      <div class="row-bottom">
        <span class="favorite-count">${svgIcon("heart")} ${Number(project.favorites_count || 0)} favoris</span>
      </div>
    </div>
    <button class="row-open" type="button" aria-label="Voir ${escapeHtml(project.name)}">${svgIcon("chevron")}</button>`;
  applyProjectIcon(article.querySelector(".project-icon"), project);
  article.querySelector(".row-open").addEventListener("click", () => openProject(project.slug));
  article.querySelector(".project-icon").addEventListener("click", () => openProject(project.slug));
  article.querySelector(".row-details").addEventListener("click", () => openProject(project.slug));
  article.querySelector(".project-icon").style.cursor = "pointer";
  return article;
}

function favoriteButtonMarkup(project) {
  const active = favoriteSlugs.has(project.slug);
  return `<button class="project-favorite ${active ? "is-active" : ""}" type="button" aria-label="${active ? "Retirer des favoris" : "Ajouter aux favoris"}" aria-pressed="${active}">${svgIcon("heart")}</button>`;
}

function bindFavoriteButton(button, project, container) {
  if (!button) return;
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      await WebStoreAPI.trackVisitor();
      const result = await WebStoreAPI.toggleFavorite(project.slug);
      if (result.is_favorite) favoriteSlugs.add(project.slug);
      else favoriteSlugs.delete(project.slug);
      project.favorites_count = result.favorites_count;
      button.classList.toggle("is-active", result.is_favorite);
      button.setAttribute("aria-pressed", String(result.is_favorite));
      button.setAttribute("aria-label", result.is_favorite ? "Retirer des favoris" : "Ajouter aux favoris");
      container.querySelectorAll(".favorite-count").forEach((count) => {
        count.innerHTML = `${svgIcon("heart")} ${Number(result.favorites_count || 0)} favoris`;
      });
      if (favoritesOnly && !result.is_favorite) renderProjects();
    } catch (_) {
      alert("Impossible de mettre ce projet en favoris. Réessayez.");
    } finally {
      button.disabled = false;
    }
  });
}

function applyProjectIcon(box, project) {
  const path = project.icon_url || project.icon_data;
  if (!box || typeof path !== "string" || !path) return;
  const image = document.createElement("img");
  image.alt = "";
  image.loading = "lazy";
  image.decoding = "async";
  image.onerror = () => { box.textContent = initials(project.name); };
  image.src = path.startsWith("data:") || /^https?:\/\//i.test(path)
    ? path : WebStoreAPI.getAssetUrl(path);
  box.replaceChildren(image);
}

function openProject(slug) {
  location.href = `pages/project.html?slug=${encodeURIComponent(slug)}`;
}

function showProjectError() {
  const empty = document.getElementById("empty");
  if (empty) {
    empty.hidden = false;
    empty.textContent = "Impossible de charger les projets pour le moment. Vérifiez votre connexion puis réessayez.";
  }
}

function initials(name) {
  return String(name || "WS").trim().split(/\s+/).map((word) => word[0]).join("").slice(0, 2).toUpperCase();
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value ?? "");
  return div.innerHTML;
}

function bindInstallPrompt() {
  const button = document.getElementById("appActionBtn");
  if (!button) return;
  const installed = () => window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  const update = () => {
    button.hidden = false;
    button.textContent = installed() ? "Partager" : "Installer";
  };
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt = event;
    update();
  });
  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    update();
  });
  button.addEventListener("click", async () => {
    if (installed()) {
      const data = { title: document.title, text: "Découvre WEB STORE", url: location.href };
      if (navigator.share) {
        try { await navigator.share(data); } catch (_) {}
      } else if (navigator.clipboard?.writeText) {
        try { await navigator.clipboard.writeText(location.href); button.textContent = "Lien copié"; setTimeout(update, 1800); }
        catch (_) { window.prompt("Copiez le lien :", location.href); }
      } else window.prompt("Copiez le lien :", location.href);
      return;
    }
    if (deferredInstallPrompt) {
      deferredInstallPrompt.prompt();
      await deferredInstallPrompt.userChoice;
      deferredInstallPrompt = null;
      update();
    } else {
      alert("Ouvrez le menu du navigateur puis choisissez « Installer l’application » ou « Ajouter à l’écran d’accueil ».");
    }
  });
  update();
  window.matchMedia("(display-mode: standalone)").addEventListener?.("change", update);
}

function bindOfflineBanner() {
  const banner = document.getElementById("offlineBanner");
  if (!banner) return;
  const update = () => { banner.hidden = navigator.onLine; };
  window.addEventListener("online", update);
  window.addEventListener("offline", update);
  update();
}
