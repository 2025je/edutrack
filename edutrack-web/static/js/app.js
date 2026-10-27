// Inicialización de la página; `first` es true solo en la carga completa (no al cambiar el contenido).
window.edutrackBoot = function (first) {
  (function(){
    function setup(){
      document.querySelectorAll("main table").forEach(function(t){
        if(!t.closest(".table-wrap")){
          var w=document.createElement("div");w.className="table-wrap";
          t.parentNode.insertBefore(w,t);w.appendChild(t);
        }
      });
      document.querySelectorAll("main .table-wrap").forEach(function(w){
        var hint=w.previousElementSibling,has=hint&&hint.classList.contains("table-scroll-hint");
        var over=w.scrollWidth>w.clientWidth+2;
        if(over&&!has&&window.innerWidth<=992){
          hint=document.createElement("p");hint.className="table-scroll-hint muted";
          hint.textContent="Desliza la tabla horizontalmente para ver todas las columnas.";
          w.parentNode.insertBefore(hint,w);has=true;
        }
        if(has)hint.classList.toggle("show",over);
      });
    }
    setup();
    if(first){window.addEventListener("resize",setup);document.addEventListener("live-filter:updated",setup);}
  })();
  (function(){
    if(!first)return;
    var lb=document.createElement("div");lb.id="lightbox";lb.setAttribute("role","dialog");lb.setAttribute("aria-label","Vista ampliada");
    lb.innerHTML='<div class="lb-bar"><button type="button" data-a="out" aria-label="Alejar"><i class="material-icons">zoom_out</i></button><button type="button" data-a="in" aria-label="Acercar"><i class="material-icons">zoom_in</i></button><button type="button" data-a="reset" aria-label="Restablecer"><i class="material-icons">fit_screen</i></button><a data-a="open" target="_blank" rel="noopener" aria-label="Abrir en otra pesta\u00f1a"><i class="material-icons">open_in_new</i></a><button type="button" data-a="close" aria-label="Cerrar"><i class="material-icons">close</i></button></div><div class="lb-stage"><img alt="Imagen ampliada"></div>';
    document.body.appendChild(lb);
    var img=lb.querySelector("img"),stage=lb.querySelector(".lb-stage"),open=lb.querySelector('[data-a=open]');
    var scale=1,x=0,y=0,drag=null;
    function paint(){img.style.transform="translate("+x+"px,"+y+"px) scale("+scale+")";}
    function zoom(f){scale=Math.min(8,Math.max(1,scale*f));if(scale===1){x=0;y=0;}paint();}
    function show(src){scale=1;x=0;y=0;paint();img.src=src;open.href=src;lb.classList.add("open");document.body.style.overflow="hidden";}
    function hide(){lb.classList.remove("open");document.body.style.overflow="";img.removeAttribute("src");}
    document.addEventListener("click",function(e){
      var el=e.target.closest("[data-zoom]");
      if(el&&!lb.contains(el)){var src=el.getAttribute("href")||el.currentSrc||el.src;if(src){e.preventDefault();show(src);}return;}
      var b=e.target.closest("#lightbox [data-a]");
      if(b){var a=b.dataset.a;if(a==="in")zoom(1.4);else if(a==="out")zoom(1/1.4);else if(a==="reset"){scale=1;x=0;y=0;paint();}else if(a==="close")hide();return;}
      if(e.target===lb||e.target===stage)hide();
    });
    document.addEventListener("keydown",function(e){
      if(!lb.classList.contains("open"))return;
      if(e.key==="Escape")hide();else if(e.key==="+"||e.key==="=")zoom(1.4);else if(e.key==="-")zoom(1/1.4);
    });
    stage.addEventListener("wheel",function(e){e.preventDefault();zoom(e.deltaY<0?1.2:1/1.2);},{passive:false});
    img.addEventListener("dblclick",function(){if(scale>1){scale=1;x=0;y=0;}else scale=2.5;paint();});
    img.addEventListener("pointerdown",function(e){if(scale<=1)return;drag={px:e.clientX,py:e.clientY,x:x,y:y};img.setPointerCapture(e.pointerId);img.style.cursor="grabbing";});
    img.addEventListener("pointermove",function(e){if(!drag)return;x=drag.x+e.clientX-drag.px;y=drag.y+e.clientY-drag.py;paint();});
    img.addEventListener("pointerup",function(){drag=null;img.style.cursor="";});
  })();
  (function(){
    function clean(th){return th.textContent.replace(/\s+/g," ").trim();}
    function val(td){
      var t=td?td.textContent.replace(/\s+/g," ").trim():"";
      var d=t.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
      if(d)return {n:+(d[3]+d[2]+d[1])};
      var num=t.replace(/^S\/\s*/,"").replace(/,/g,"");
      if(/^-?\d+(\.\d+)?$/.test(num))return {n:parseFloat(num)};
      return {s:t.toLowerCase()};
    }
    function cmp(a,b){
      if(a.n!==undefined&&b.n!==undefined)return a.n-b.n;
      if(a.n!==undefined)return -1;if(b.n!==undefined)return 1;
      if(a.s===""&&b.s!=="")return 1;if(b.s===""&&a.s!=="")return -1;
      return a.s.localeCompare(b.s,"es",{numeric:true});
    }
    function sortBy(table,th,idx){
      var dir=th.getAttribute("aria-sort")==="ascending"?"descending":"ascending";
      table.querySelectorAll("th[data-sortable]").forEach(function(h){h.removeAttribute("aria-sort");});
      th.setAttribute("aria-sort",dir);
      var body=table.tBodies[0];
      var rows=Array.prototype.filter.call(body.rows,function(r){return r.cells.length>idx&&!r.querySelector("td[colspan]");});
      var keyed=rows.map(function(r,i){return {r:r,i:i,v:val(r.cells[idx])};});
      keyed.sort(function(a,b){var c=cmp(a.v,b.v);if(dir==="descending")c=-c;return c||a.i-b.i;});
      keyed.forEach(function(k){body.appendChild(k.r);});
    }
    function init(){
      document.querySelectorAll("main table:not([data-no-sort])").forEach(function(table){
        if(!table.tHead||!table.tBodies[0])return;
        var ths=table.tHead.rows[table.tHead.rows.length-1].cells;
        Array.prototype.forEach.call(ths,function(th,idx){
          if(th.dataset.sortable!==undefined||th.querySelector("a")||th.querySelector("input")||!clean(th)||/^acci/i.test(clean(th)))return;
          th.setAttribute("data-sortable","");th.title="Ordenar por esta columna (p\u00e1gina actual)";
          th.addEventListener("click",function(){sortBy(table,th,idx);});
        });
      });
    }
    init();if(first)document.addEventListener("live-filter:updated",init);
  })();
  (function(){
    var form=document.querySelector("form[data-live-filter]");
    if(!form||!window.localStorage)return;
    var key="edutrack:filters:"+location.pathname,saved={};
    try{saved=JSON.parse(localStorage.getItem(key)||"{}");}catch(e){saved={};}
    var bar=document.createElement("div");bar.className="saved-filters no-print";
    bar.innerHTML='<span class="chip-label"><i class="material-icons tiny" style="vertical-align:middle">bookmark</i> Filtros guardados</span><select class="browser-default" aria-label="Filtros guardados"></select><button type="button" class="btn-small blue darken-2" data-sf="save">Guardar actual</button><button type="button" class="btn-flat red-text" data-sf="del">Eliminar</button>';
    var sel=bar.querySelector("select");
    function fill(current){
      sel.innerHTML='<option value="">Seleccionar\u2026</option>';
      Object.keys(saved).sort().forEach(function(n){var o=document.createElement("option");o.value=n;o.textContent=n;if(n===current)o.selected=true;sel.appendChild(o);});
    }
    function persist(){localStorage.setItem(key,JSON.stringify(saved));}
    function currentQuery(){
      var p=new URLSearchParams();
      new FormData(form).forEach(function(v,k){if(v!==""&&k!=="page"&&k!=="csrfmiddlewaretoken")p.append(k,v);});
      return p.toString();
    }
    fill();
    sel.addEventListener("change",function(){
      if(!sel.value)return;
      var qs=saved[sel.value];
      location.href=location.pathname+(qs?"?"+qs:"");
    });
    bar.addEventListener("click",function(e){
      var b=e.target.closest("[data-sf]");if(!b)return;
      if(b.dataset.sf==="save"){
        var qs=currentQuery();
        if(!qs){alert("Aplica al menos un filtro antes de guardarlo.");return;}
        var name=(prompt("Nombre para este filtro:")||"").trim().slice(0,40);
        if(!name)return;
        saved[name]=qs;persist();fill(name);
      }else if(sel.value&&confirm("\u00bfEliminar el filtro \u00ab"+sel.value+"\u00bb?")){
        delete saved[sel.value];persist();fill();
      }
    });
    form.parentNode.insertBefore(bar,form.nextSibling);
  })();
  (function(){
    var icons=[["personales","person"],["contacto","contact_phone"],["estado","toggle_on"],["matr","assignment"],["promotor","badge"],["ficha","description"],["costo","payments"],["curso","menu_book"],["alumno","school"],["estudiante","school"],["usuario","person"],["recibo","receipt_long"],["importe","attach_money"],["deuda","money_off"],["fecha","event"],["inicio","event"],["pago","payments"],["adicional","info"],["voucher","image"],["acceso","vpn_key"],["permiso","security"],["sede","apartment"],["identidad","palette"],["volante","picture_as_pdf"],["qui","manage_search"],["cu\u00e1ndo","schedule"],["asignaci","assignment_ind"]];
    document.querySelectorAll("form h6.strong, h2.section-title").forEach(function(h){
      if(h.querySelector(".title-icon"))return;
      var t=h.textContent.toLowerCase(),name="label";
      for(var i=0;i<icons.length;i++){if(t.indexOf(icons[i][0])!==-1){name=icons[i][1];break;}}
      var s=document.createElement("span");s.className="title-icon";s.setAttribute("aria-hidden","true");
      s.innerHTML='<i class="material-icons">'+name+'</i>';
      h.insertBefore(s,h.firstChild);h.classList.add("has-title-icon");
    });
  })();
  if (first) {
  M.Sidenav.init(document.querySelectorAll(".sidenav"));
  var toggle = document.getElementById("theme-toggle");
  var THEMES = ["light", "dark", "system"];
  var LABELS = {light: "Modo claro", dark: "Modo oscuro", system: "Automático"};
  var ICONS = {light: "light_mode", dark: "dark_mode", system: "brightness_auto"};
  var media = window.matchMedia("(prefers-color-scheme: dark)");
  function savedTheme() {
    var value = null;
    try { value = localStorage.getItem("theme"); } catch (e) {}
    return THEMES.indexOf(value) === -1 ? "system" : value;
  }
  function applyTheme(mode) {
    var dark = mode === "dark" || (mode === "system" && media.matches);
    if (dark) document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
    toggle.querySelector("i").textContent = ICONS[mode];
    var next = LABELS[THEMES[(THEMES.indexOf(mode) + 1) % THEMES.length]];
    toggle.title = LABELS[mode] + " (clic para cambiar a: " + next + ")";
    toggle.setAttribute("aria-label", "Tema: " + LABELS[mode] + ". Cambiar a: " + next);
  }
  applyTheme(savedTheme());
  toggle.addEventListener("click", function () {
    var mode = THEMES[(THEMES.indexOf(savedTheme()) + 1) % THEMES.length];
    try { localStorage.setItem("theme", mode); } catch (e) {}
    applyTheme(mode);
  });
  media.addEventListener("change", function () {
    if (savedTheme() === "system") applyTheme("system");
  });
  }
  document.querySelectorAll("select").forEach(function (el) { el.classList.add("browser-default"); });
  document.querySelectorAll("input[type=checkbox],input[type=radio]").forEach(function (el) {
    var next = el.nextElementSibling;
    if (!next || next.tagName !== "SPAN") el.classList.add("browser-default");
  });
  document.querySelectorAll("textarea").forEach(function (el) { el.classList.add("materialize-textarea"); });
  };
  document.addEventListener("DOMContentLoaded", function () { window.edutrackBoot(true); });

// Convierte a mayúsculas lo que se escribe en campos de texto (excepto usuario, correo, contraseña y URLs).
(function () {
  var isLogin = /login|acceso|ingresar/i.test(location.pathname);
  var skipNames = isLogin ? /(username|email|password|url|token)/i : /(email|password|url|token)/i;
  function applies(el) {
    if (el.tagName === "TEXTAREA") return !el.hasAttribute("data-no-upper");
    if (el.tagName !== "INPUT" || el.hasAttribute("data-no-upper")) return false;
    var t = (el.getAttribute("type") || "text").toLowerCase();
    if (t !== "text" && t !== "search") return false;
    return !skipNames.test(el.name || "") && !skipNames.test(el.autocomplete || "");
  }
  document.addEventListener("input", function (e) {
    var el = e.target;
    if (!applies(el) || e.isComposing) return;
    var up = el.value.toUpperCase();
    if (up === el.value) return;
    var s = el.selectionStart, end = el.selectionEnd;
    el.value = up;
    try { el.setSelectionRange(s, end); } catch (err) {}
  }, true);
})();

// Filtros plegables: los campos con data-primary quedan visibles; el resto se agrupa en "Más filtros".
// Los filtros aplicados se muestran como chips que se pueden quitar uno a uno.
window.edutrackFilters = function () {
  document.querySelectorAll("form[data-filter-collapse]:not([data-filter-ready])").forEach(function (form) {
    form.setAttribute("data-filter-ready", "");
    var extra = [];
    var actions = null;
    var pending = null;
    Array.prototype.slice.call(form.children).forEach(function (el) {
      if (el.hasAttribute("data-actions")) { actions = el; return; }
      if (el.tagName === "INPUT" || el.tagName === "STYLE") return;
      if (/^H[1-6]$/.test(el.tagName)) {
        var next = el.nextElementSibling;
        pending = el;
        // Con filas anidadas el título se queda visible mientras haya campos principales debajo.
        if (!(next && next.classList.contains("row"))) el.hidden = true;
        return;
      }
      if (el.classList.contains("row")) {
        var rest = Array.prototype.slice.call(el.children).filter(function (c) { return !c.hasAttribute("data-primary"); });
        if (rest.length === el.children.length) {
          if (pending) extra.push(pending);
          extra.push(el);
        } else if (rest.length) {
          var overflow = document.createElement("div");
          overflow.className = "row";
          rest.forEach(function (c) { overflow.appendChild(c); });
          extra.push(overflow);
        }
        pending = null;
        return;
      }
      if (el.hasAttribute("data-primary")) return;
      if (pending && pending.hidden) { pending.hidden = false; extra.push(pending); pending = null; }
      extra.push(el);
    });
    if (!actions || !extra.length) return;

    var more = document.createElement("div");
    more.className = "col s12 filter-more";
    var inner = document.createElement("div");
    inner.className = "row";
    extra.forEach(function (el) { inner.appendChild(el); });
    more.appendChild(inner);
    more.hidden = true;

    var chips = document.createElement("div");
    chips.className = "col s12 filter-chips";
    chips.hidden = true;

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "btn-flat blue-text filter-toggle";
    toggle.setAttribute("aria-expanded", "false");
    actions.insertBefore(toggle, actions.firstChild);
    actions.classList.add("filter-actions");
    form.insertBefore(chips, actions.nextSibling);
    form.insertBefore(more, chips.nextSibling);

    function fields(root) {
      return Array.prototype.slice.call(root.querySelectorAll("input:not([type=hidden]):not([type=submit]), select"));
    }
    function isActive(field) {
      if (field.closest("[data-nochip]")) return false;
      return field.type === "checkbox" ? field.checked : field.value !== "";
    }
    function labelOf(field) {
      if (field.type === "checkbox") {
        var wrap = field.closest("label");
        return wrap ? wrap.textContent.trim() : field.name;
      }
      var label = field.id && form.querySelector('label[for="' + field.id + '"]');
      return label ? label.textContent.trim() : (field.getAttribute("aria-label") || field.name);
    }
    function displayValue(field) {
      if (field.tagName === "SELECT") return field.selectedOptions.length ? field.selectedOptions[0].textContent.trim() : "";
      return field.value.trim();
    }
    function setOpen(open) {
      more.hidden = !open;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      refresh();
    }
    function refresh() {
      var hiddenCount = fields(inner).filter(isActive).length;
      var open = !more.hidden;
      toggle.textContent = (open ? "Menos filtros" : "Más filtros") + (hiddenCount ? " (" + hiddenCount + ")" : "");
      chips.textContent = "";
      var active = fields(form).filter(isActive);
      active.forEach(function (field) {
        var chip = document.createElement("span");
        chip.className = "filter-chip";
        chip.appendChild(document.createTextNode(field.type === "checkbox" ? labelOf(field) + " " : labelOf(field) + ": " + displayValue(field) + " "));
        var remove = document.createElement("button");
        remove.type = "button";
        remove.setAttribute("aria-label", "Quitar filtro " + labelOf(field));
        remove.textContent = "✕";
        remove.addEventListener("click", function () {
          if (field.type === "checkbox") field.checked = false; else field.value = "";
          field.dispatchEvent(new Event(field.matches("select, input[type=date]") ? "change" : "input", {bubbles: true}));
        });
        chip.appendChild(remove);
        chips.appendChild(chip);
      });
      chips.hidden = !active.length;
    }

    toggle.addEventListener("click", function () { setOpen(more.hidden); });
    form.addEventListener("input", refresh);
    form.addEventListener("change", refresh);
    setOpen(fields(inner).some(isActive));
  });
};

// Filtrado en vivo: el formulario con data-live-filter actualiza las zonas data-live-region sin recargar.
window.edutrackLive = function () {
  if (window.edutrackFilters) window.edutrackFilters();
  var form = document.querySelector("form[data-live-filter]");
  window.__liveLoad = null;
  if (!form) return;
  var controller = null;
  var timer = null;

  function queryString() {
    var params = new URLSearchParams();
    var current = new URLSearchParams(location.search);
    ["sort", "direction"].forEach(function (key) {
      if (current.has(key) && !form.elements[key]) params.set(key, current.get(key));
    });
    new FormData(form).forEach(function (value, key) {
      if (value !== "" && key !== "page") params.append(key, value);
    });
    return params.toString();
  }

  function syncExports(url) {
    var params = new URL(url, location.href).searchParams;
    params.delete("page");
    document.querySelectorAll("[data-live-export]").forEach(function (link) {
      var parts = [params.toString(), link.dataset.liveExtra].filter(Boolean);
      link.href = link.dataset.liveExport + (parts.length ? "?" + parts.join("&") : "");
    });
  }

  function load(url) {
    if (controller) controller.abort();
    controller = new AbortController();
    fetch(url, {signal: controller.signal, headers: {"X-Requested-With": "XMLHttpRequest"}})
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        document.querySelectorAll("[data-live-region]").forEach(function (region) {
          var fresh = doc.querySelector('[data-live-region="' + region.dataset.liveRegion + '"]');
          if (!fresh) return;
          var checked = region.querySelector("input[type=radio]:checked");
          var checkedValue = checked ? checked.value : null;
          region.innerHTML = fresh.innerHTML;
          if (checkedValue !== null) {
            region.querySelectorAll("input[type=radio]").forEach(function (radio) {
              if (radio.value === checkedValue) radio.checked = true;
            });
          }
        });
        history.replaceState(null, "", url);
        syncExports(url);
        document.dispatchEvent(new Event("live-filter:updated"));
      })
      .catch(function (error) {
        if (error.name !== "AbortError") console.error(error);
      });
  }

  function run() {
    clearTimeout(timer);
    var qs = queryString();
    load(location.pathname + (qs ? "?" + qs : ""));
  }

  form.addEventListener("input", function (event) {
    if (event.target.matches("select, input[type=date]")) return;
    clearTimeout(timer);
    timer = setTimeout(run, 300);
  });
  form.addEventListener("change", function (event) {
    if (event.target.matches("select, input[type=date]")) run();
  });
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    run();
  });
  window.__liveLoad = load;
};
document.addEventListener("click", function (event) {
  if (!window.__liveLoad) return;
  var link = event.target.closest("a");
  if (!link || !link.closest("[data-live-region]")) return;
  if (!link.closest(".pager, thead")) return;
  event.preventDefault();
  window.__liveLoad(link.href);
});
document.addEventListener("DOMContentLoaded", window.edutrackLive);

document.addEventListener("input", function (e) {
  var input = e.target;
  if (!input.matches || !input.matches("input[data-uppercase]")) return;
  var upper = input.value.toUpperCase();
  if (input.value === upper) return;
  var start = input.selectionStart, end = input.selectionEnd;
  input.value = upper;
  try { input.setSelectionRange(start, end); } catch (err) {}
});

document.addEventListener("click", function (e) {
  document.querySelectorAll("details.campus-menu[open]").forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute("open"); });
});

document.addEventListener("keydown", function (e) {
  var isShortcut = e.key === "/" || (e.key.toLowerCase() === "k" && (e.ctrlKey || e.metaKey));
  if (!isShortcut || e.altKey) return;
  var t = e.target, tag = t && t.tagName;
  if (e.key === "/" && (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable))) return;
  var box = document.querySelector(".header-search input[name=q]");
  if (!box || box.offsetParent === null) return;
  e.preventDefault();
  box.focus();
  box.select();
});

// Busqueda global: resultados al escribir (secciones, subsecciones y acciones) con teclado.
(function () {
  var timer = null, seq = 0, active = -1;
  function box() { return document.querySelector(".header-search input[name=q]"); }
  function panel() {
    var p = document.getElementById("global-search-results");
    if (p) return p;
    var input = box();
    if (!input) return null;
    p = document.createElement("ul");
    p.id = "global-search-results";
    p.setAttribute("role", "listbox");
    p.hidden = true;
    input.closest(".header-search").appendChild(p);
    return p;
  }
  function close() { var p = panel(); if (p) { p.hidden = true; p.innerHTML = ""; } active = -1; }
  function mark(index) {
    var items = panel().querySelectorAll("a");
    if (!items.length) return;
    active = (index + items.length) % items.length;
    items.forEach(function (a, i) { a.classList.toggle("active", i === active); });
    items[active].scrollIntoView({ block: "nearest" });
  }
  function render(results, term) {
    var p = panel();
    p.innerHTML = "";
    if (!results.length) {
      var empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = "No hay secciones para \u00ab" + term + "\u00bb";
      p.appendChild(empty);
    }
    results.forEach(function (r) {
      var li = document.createElement("li"), a = document.createElement("a"), small = document.createElement("small");
      a.href = r.url;
      a.setAttribute("role", "option");
      a.textContent = r.name;
      small.textContent = r.group;
      a.appendChild(small);
      li.appendChild(a);
      p.appendChild(li);
    });
    p.hidden = false;
    active = -1;
  }
  function search(input) {
    var term = input.value.trim();
    if (!term) { close(); return; }
    var mine = ++seq;
    fetch(input.form.action + "?json=1&q=" + encodeURIComponent(term), { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { results: [] }; })
      .then(function (data) { if (mine === seq) render(data.results, term); })
      .catch(function () {});
  }
  document.addEventListener("input", function (e) {
    var input = box();
    if (!input || e.target !== input) return;
    clearTimeout(timer);
    timer = setTimeout(function () { search(input); }, 150);
  });
  document.addEventListener("keydown", function (e) {
    var input = box();
    if (!input || e.target !== input) return;
    var p = panel();
    if (e.key === "Escape") { close(); input.blur(); }
    else if (p && !p.hidden && e.key === "ArrowDown") { e.preventDefault(); mark(active + 1); }
    else if (p && !p.hidden && e.key === "ArrowUp") { e.preventDefault(); mark(active - 1); }
    else if (e.key === "Enter" && p && !p.hidden && active >= 0) {
      e.preventDefault();
      window.location.href = p.querySelectorAll("a")[active].href;
    }
  });
  document.addEventListener("click", function (e) {
    var input = box();
    if (input && !input.closest(".header-search").contains(e.target)) close();
  });
})();