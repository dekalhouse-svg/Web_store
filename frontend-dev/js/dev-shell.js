(function(){
  const current=(location.pathname.split("/").pop()||"dashboard.html").split("?")[0];
  document.querySelectorAll(".sidebar-nav a").forEach(a=>{
    const href=(a.getAttribute("href")||"").split("?")[0];
    if(href===current){a.classList.add("active");a.setAttribute("aria-current","page");}
    else {a.classList.remove("active");a.removeAttribute("aria-current");}
  });
})();