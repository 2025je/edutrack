(function () {
  var dialog = document.getElementById("onboarding-guide");
  if (!dialog || dialog.dataset.bound) return;
  dialog.dataset.bound = "1";
  var steps = dialog.querySelectorAll(".guide-step");
  var bars = dialog.querySelectorAll(".guide-progress span");
  var prev = dialog.querySelector('[data-guide="prev"]');
  var next = dialog.querySelector('[data-guide="next"]');
  var current = 0;
  var pending = dialog.dataset.pending === "1";

  function show(index) {
    current = Math.max(0, Math.min(steps.length - 1, index));
    steps.forEach(function (step, i) { step.hidden = i !== current; });
    bars.forEach(function (bar, i) { bar.classList.toggle("on", i <= current); });
    prev.hidden = current === 0;
    next.textContent = current === steps.length - 1 ? "Entendido" : "Siguiente";
  }

  function markSeen() {
    if (!pending) return;
    pending = false;
    var form = dialog.querySelector("form");
    fetch(dialog.dataset.url, {method: "POST", body: new FormData(form), credentials: "same-origin"}).catch(function () {
      pending = true;
    });
  }

  function open() {
    show(0);
    if (!dialog.open) dialog.showModal();
  }

  var ring = document.querySelector(".tour-ring");
  var card = document.querySelector(".tour-card");
  var tourData = document.getElementById("onboarding-tour");
  var tourSteps = [];
  var tourIndex = 0;
  var handoff = false;

  function visibleLink(url) {
    var link = document.querySelector('#slide-out a[href="' + url + '"]');
    if (!link) return null;
    var group = link.closest("details");
    if (group) group.open = true;
    return link.getClientRects().length ? link : null;
  }

  function collectTour() {
    if (window.matchMedia("(max-width: 992px)").matches) return [];
    var items = tourData ? JSON.parse(tourData.textContent) : [];
    return items.map(function (item) {
      item.link = visibleLink(item.url);
      return item;
    }).filter(function (item) { return item.link; });
  }

  function place() {
    var item = tourSteps[tourIndex];
    var rect = item.link.getBoundingClientRect();
    var pad = 4;
    ring.style.cssText = "top:" + (rect.top - pad) + "px;left:" + (rect.left - pad) + "px;width:" +
      (rect.width + pad * 2) + "px;height:" + (rect.height + pad * 2) + "px";
    var gap = 16;
    var cardWidth = card.offsetWidth;
    var cardHeight = card.offsetHeight;
    var left = rect.right + gap;
    if (left + cardWidth > window.innerWidth - 8) left = Math.max(8, window.innerWidth - cardWidth - 8);
    var top = Math.min(Math.max(8, rect.top - 8), window.innerHeight - cardHeight - 8);
    card.style.left = left + "px";
    card.style.top = Math.max(8, top) + "px";
  }

  function showTour(index) {
    tourIndex = index;
    var item = tourSteps[index];
    item.link.scrollIntoView({block: "center"});
    card.querySelector(".tour-head i").textContent = item.icon;
    card.querySelector("h3").textContent = item.title;
    card.querySelector(".tour-summary").textContent = item.summary;
    var list = card.querySelector(".tour-actions");
    list.textContent = "";
    item.actions.forEach(function (text) {
      var li = document.createElement("li");
      li.textContent = text;
      list.appendChild(li);
    });
    card.querySelector(".tour-count").textContent = (index + 1) + " de " + tourSteps.length;
    card.querySelector('[data-tour="prev"]').hidden = index === 0;
    card.querySelector('[data-tour="next"]').textContent = index === tourSteps.length - 1 ? "Finalizar" : "Siguiente";
    ring.hidden = false;
    card.hidden = false;
    place();
  }

  function endTour(finish) {
    ring.hidden = true;
    card.hidden = true;
    window.removeEventListener("resize", place);
    if (finish) {
      show(1);
      if (!dialog.open) dialog.showModal();
    } else {
      markSeen();
    }
  }

  function startTour() {
    tourSteps = collectTour();
    if (!tourSteps.length) { show(1); return; }
    handoff = true;
    dialog.close();
    window.addEventListener("resize", place);
    showTour(0);
  }

  card.querySelector('[data-tour="next"]').addEventListener("click", function () {
    if (tourIndex === tourSteps.length - 1) endTour(true);
    else showTour(tourIndex + 1);
  });
  card.querySelector('[data-tour="prev"]').addEventListener("click", function () { showTour(tourIndex - 1); });
  card.querySelector('[data-tour="skip"]').addEventListener("click", function () { endTour(false); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !card.hidden) endTour(false);
  });

  next.addEventListener("click", function () {
    if (current === steps.length - 1) dialog.close();
    else if (current === 0 && tourData) startTour();
    else show(current + 1);
  });
  prev.addEventListener("click", function () { show(current - 1); });
  dialog.querySelector('[data-guide="skip"]').addEventListener("click", function () { dialog.close(); });
  dialog.addEventListener("close", function () {
    if (handoff) { handoff = false; return; }
    markSeen();
  });
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-open-guide]")) { event.preventDefault(); open(); }
  });

  if (pending && typeof dialog.showModal === "function") open();
})();
