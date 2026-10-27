// Menú contraído (solo escritorio): se recuerda en localStorage.
(function () {
  var KEY = "edutrack.sidebar.collapsed";
  function stored() { try { return localStorage.getItem(KEY) === "1"; } catch (e) { return false; } }
  document.body.classList.toggle("side-collapsed", stored());

  // Cargas completas: se recuerda la posición del scroll del menú.
  var SCROLL_KEY = "edutrack.sidebar.scroll";
  var scroller = document.querySelector("#slide-out .sidenav-scroll");
  if (scroller) {
    try { scroller.scrollTop = parseInt(sessionStorage.getItem(SCROLL_KEY), 10) || 0; } catch (e) {}
    window.addEventListener("pagehide", function () {
      var current = document.querySelector("#slide-out .sidenav-scroll");
      try { if (current) sessionStorage.setItem(SCROLL_KEY, current.scrollTop); } catch (e) {}
    });
  }

  document.addEventListener("click", function (event) {
    if (!event.target.closest("#sidebar-toggle")) return;
    var collapsed = document.body.classList.toggle("side-collapsed");
    try { localStorage.setItem(KEY, collapsed ? "1" : "0"); } catch (e) {}
    window.dispatchEvent(new Event("resize"));
  });
})();

// Navegación parcial: enlaces y formularios del menú, del contenido y del buscador solo reemplazan <main>.
(function () {
  var controller = null;
  var lastUrl = location.href.split("#")[0];

  function labelLinks() {
    document.querySelectorAll("#slide-out li > a").forEach(function (a) {
      if (a.classList.contains("account-box")) return;
      a.title = Array.prototype.filter.call(a.childNodes, function (n) { return n.nodeType === 3; })
        .map(function (n) { return n.textContent; }).join(" ").replace(/\s+/g, " ").trim();
    });
    var campus = document.querySelector("#slide-out .sidebar-campus summary");
    var name = document.querySelector("#slide-out .sidebar-campus strong");
    if (campus && name) campus.title = "Campus actual: " + name.textContent.trim();
  }

  function highlight() {
    var path = location.pathname, best = null;
    document.querySelectorAll("#slide-out a[href]").forEach(function (a) {
      a.classList.remove("active");
      a.removeAttribute("aria-current");
      var h = a.getAttribute("href");
      if (h === path || (h.length > 1 && path.indexOf(h) === 0)) {
        if (!best || h.length > best.getAttribute("href").length) best = a;
      }
    });
    if (best) {
      best.classList.add("active");
      best.setAttribute("aria-current", "page");
    }
    labelLinks();
  }

  function runScripts(container) {
    var pending = [];
    var original = document.addEventListener;
    document.addEventListener = function (type, fn, opts) {
      if (type === "DOMContentLoaded") pending.push(fn);
      else original.call(document, type, fn, opts);
    };
    try {
      container.querySelectorAll("script").forEach(function (old) {
        var fresh = document.createElement("script");
        Array.prototype.forEach.call(old.attributes, function (attr) { fresh.setAttribute(attr.name, attr.value); });
        fresh.text = old.textContent;
        old.replaceWith(fresh);
      });
    } finally {
      document.addEventListener = original;
    }
    pending.forEach(function (fn) { fn.call(document, new Event("DOMContentLoaded")); });
  }

  function download(response) {
    var disposition = response.headers.get("content-disposition") || "";
    var match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
    var name = match ? decodeURIComponent(match[1]) : "descarga";
    return response.blob().then(function (blob) {
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 10000);
    });
  }

  // Precarga al pasar el cursor por el menú: el clic reutiliza la respuesta si es reciente (una sola vez).
  var prefetched = {};
  var hoverTimer = null;
  function prefetchable(link) {
    return link && link.closest("#slide-out") && !link.target && !link.hasAttribute("download") &&
      !link.hasAttribute("data-full") && !link.hasAttribute("data-live-export") && internal(link) &&
      link.getAttribute("href") && link.getAttribute("href").charAt(0) !== "#" && link.href !== location.href;
  }
  function prefetch(link) {
    var entry = prefetched[link.href];
    if (entry && Date.now() - entry.time < 15000) return;
    prefetched[link.href] = {
      time: Date.now(),
      promise: fetch(link.href, {credentials: "same-origin"}).catch(function () { return null; })
    };
  }
  document.addEventListener("mouseover", function (event) {
    var link = event.target.closest && event.target.closest("a[href]");
    if (!prefetchable(link)) return;
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(function () { prefetch(link); }, 90);
  });
  document.addEventListener("mouseout", function () { clearTimeout(hoverTimer); });

  function request_(request, method, signal) {
    var entry = method === "GET" ? prefetched[request.url] : null;
    if (entry) {
      delete prefetched[request.url];
      if (Date.now() - entry.time < 15000) {
        return entry.promise.then(function (response) {
          return response && response.ok ? response : fetch(request.url, {signal: signal, credentials: "same-origin"});
        });
      }
    }
    return fetch(request.url, {method: method, body: request.body, signal: signal, credentials: "same-origin"});
  }

  // request: {url, method, body}. Si algo no se puede mostrar parcialmente, se cae a la carga completa.
  function navigate(request, push) {
    var main = document.querySelector("main");
    var method = request.method || "GET";
    if (method !== "GET") prefetched = {};
    if (controller) controller.abort();
    controller = new AbortController();
    main.classList.add("is-loading");
    document.documentElement.classList.add("nav-busy");

    function fallback(html, url) {
      if (method === "GET" || html === null) { window.location.href = request.url; return; }
      // Una respuesta a un POST no se puede repetir con un GET: se muestra tal cual.
      history.pushState(null, "", url);
      document.open();
      document.write(html);
      document.close();
    }

    request_(request, method, controller.signal)
      .then(function (response) {
        var type = response.headers.get("content-type") || "";
        var attachment = /attachment/i.test(response.headers.get("content-disposition") || "");
        if (type.indexOf("text/html") === -1 || attachment) {
          if (method === "GET" && !attachment) throw new Error("not-html");
          return download(response).then(function () { main.classList.remove("is-loading"); document.documentElement.classList.remove("nav-busy"); });
        }
        return response.text().then(function (html) {
          var doc = new DOMParser().parseFromString(html, "text/html");
          var fresh = doc.querySelector("main");
          var menu = doc.getElementById("slide-out");
          if (!fresh || !menu) return fallback(method === "GET" ? null : html, response.url);
          var scroller = document.querySelector("#slide-out .sidenav-scroll");
          var menuScroll = scroller ? scroller.scrollTop : 0;
          main.innerHTML = fresh.innerHTML;
          document.getElementById("slide-out").innerHTML = menu.innerHTML;
          var newScroller = document.querySelector("#slide-out .sidenav-scroll");
          if (newScroller) newScroller.scrollTop = menuScroll;
          var search = document.querySelector("header .header-search");
          var freshSearch = doc.querySelector("header .header-search");
          if (search && freshSearch) search.innerHTML = freshSearch.innerHTML;
          document.title = doc.title;
          if (push && response.url !== location.href) history.pushState(null, "", response.url);
          else if (response.url !== location.href) history.replaceState(null, "", response.url);
          lastUrl = location.href.split("#")[0];
          window.scrollTo(0, 0);
          highlight();
          runScripts(main);
          window.edutrackBoot(false);
          window.edutrackLive();
          main.classList.remove("is-loading");
          document.documentElement.classList.remove("nav-busy");
          main.classList.remove("is-entering");
          void main.offsetWidth;
          main.classList.add("is-entering");
          main.addEventListener("animationend", function done() {
            main.classList.remove("is-entering");
            main.removeEventListener("animationend", done);
          });
        });
      })
      .catch(function (error) {
        if (error.name === "AbortError") return;
        main.classList.remove("is-loading");
        document.documentElement.classList.remove("nav-busy");
        if (method === "GET") window.location.href = request.url;
        else console.error(error);
      });
  }

  function ready() { return window.edutrackBoot && window.edutrackLive; }

  function internal(url) {
    return url.origin === location.origin && !/^\/(admin|media|static)\//.test(url.pathname);
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest("a[href]");
    if (!link || event.defaultPrevented || event.button !== 0) return;
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    if (!link.closest("#slide-out, main, header .brand-logo, header")) return;
    if (link.target || link.hasAttribute("download") || link.hasAttribute("data-zoom") ||
        link.hasAttribute("data-live-export") || link.hasAttribute("data-full")) return;
    if (link.closest("[data-live-region]") && link.closest(".pager, thead") && window.__liveLoad) return;
    var href = link.getAttribute("href");
    if (!href || href.charAt(0) === "#" || /^(javascript|mailto|tel):/i.test(href)) return;
    if (!internal(link) || !ready()) return;
    event.preventDefault();
    if (link.closest("#slide-out") && window.M && window.innerWidth <= 992) {
      var drawer = M.Sidenav.getInstance(document.getElementById("slide-out"));
      if (drawer && drawer.isOpen) drawer.close();
    }
    if (link.href === location.href) return;
    navigate({url: link.href}, true);
  });

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (event.defaultPrevented || !form.matches || !form.closest("#slide-out, main, header .header-search")) return;
    if (form.target || form.hasAttribute("data-full") || !ready()) return;
    var submitter = event.submitter;
    var action = new URL((submitter && submitter.getAttribute("formaction")) || form.getAttribute("action") || location.href, location.href);
    var method = ((submitter && submitter.getAttribute("formmethod")) || form.getAttribute("method") || "GET").toUpperCase();
    if (!internal(action) || (method !== "GET" && method !== "POST")) return;
    var data = new FormData(form);
    if (submitter && submitter.name) data.append(submitter.name, submitter.value);
    event.preventDefault();
    if (method === "GET") {
      var params = new URLSearchParams();
      data.forEach(function (value, key) { if (typeof value === "string") params.append(key, value); });
      action.search = params.toString();
      navigate({url: action.href}, true);
    } else {
      navigate({url: action.href, method: "POST", body: data}, true);
    }
  });

  window.addEventListener("popstate", function () {
    var current = location.href.split("#")[0];
    if (current === lastUrl) return;
    navigate({url: location.href}, false);
  });
  highlight();
})();
