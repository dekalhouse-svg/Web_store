(function(){
  const current=(location.pathname.split("/").pop()||"dashboard.html").split("?")[0];
  document.querySelectorAll(".sidebar-nav a").forEach(a=>{
    const href=(a.getAttribute("href")||"").split("?")[0];
    if(href===current){a.classList.add("active");a.setAttribute("aria-current","page");}
    else {a.classList.remove("active");a.removeAttribute("aria-current");}
  });

  const THEME_KEY="webstore_dev_theme";
  const root=document.documentElement;
  const media=window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  function applyTheme(choice){
    const effective=choice==="system" ? (media && media.matches ? "dark" : "light") : choice;
    root.dataset.theme=effective;
    root.dataset.themePreference=choice;
    document.querySelectorAll("[data-theme-choice]").forEach(button=>{
      button.setAttribute("aria-pressed",String(button.dataset.themeChoice===choice));
    });
  }
  let saved="system";
  try { saved=localStorage.getItem(THEME_KEY)||"system"; } catch(_) {}
  if(!["light","dark","system"].includes(saved)) saved="system";
  applyTheme(saved);
  document.querySelectorAll("[data-theme-choice]").forEach(button=>{
    button.addEventListener("click",()=>{
      const choice=button.dataset.themeChoice;
      if(!["light","dark","system"].includes(choice)) return;
      try { localStorage.setItem(THEME_KEY,choice); } catch(_) {}
      applyTheme(choice);
    });
  });
  if(media){
    const update=()=>{ if((root.dataset.themePreference||saved)==="system") applyTheme("system"); };
    if(media.addEventListener) media.addEventListener("change",update);
    else if(media.addListener) media.addListener(update);
  }
})();
