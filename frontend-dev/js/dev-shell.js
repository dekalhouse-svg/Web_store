(function(){
  const key="webstore_dev_theme";
  let preference="system";
  try{preference=localStorage.getItem(key)||"system";}catch(_){}
  const dark=preference==="dark"||(preference==="system"&&window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme=dark?"dark":"light";
  if(document.body)document.body.dataset.theme=dark?"dark":"light";
  if(preference==="system"&&window.matchMedia){
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change",event=>{
      document.documentElement.dataset.theme=event.matches?"dark":"light";
      if(document.body)document.body.dataset.theme=event.matches?"dark":"light";
    });
  }
})();
(function(){
  const current=(location.pathname.split("/").pop()||"dashboard.html").split("?")[0];
  document.querySelectorAll(".sidebar-nav a").forEach(a=>{
    const href=(a.getAttribute("href")||"").split("?")[0];
    if(href===current){a.classList.add("active");a.setAttribute("aria-current","page");}
    else {a.classList.remove("active");a.removeAttribute("aria-current");}
  });
})();