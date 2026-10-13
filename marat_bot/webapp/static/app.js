/* Mini App бота: доступ, устройства, тарифы, профиль. Данные — POST api/me с initData Telegram. */
(function () {
  "use strict";
  var tg = window.Telegram && window.Telegram.WebApp;
  var $ = function (id) { return document.getElementById(id); };
  var data = null;

  function initData() {
    if (tg && tg.initData) return tg.initData;
    var hash = new URLSearchParams(location.hash.slice(1));
    return hash.get("tgWebAppData") || "";
  }

  function plural(n, one, few, many) {
    var t = n % 100, u = n % 10;
    if (t >= 11 && t <= 14) return many;
    return u === 1 ? one : u >= 2 && u <= 4 ? few : many;
  }
  function days(n) { return n + " " + plural(n, "день", "дня", "дней"); }
  function devicesWord(n) { return plural(n, "устройство", "устройства", "устройств"); }
  function gb(bytes) { return (bytes / 1073741824).toFixed(1).replace(".", ","); }
  function rub(n) { return n.toLocaleString("ru-RU").replace(/ /g, " ") + " ₽"; }

  function haptic(kind) {
    try {
      if (!tg || !tg.HapticFeedback) return;
      if (kind === "ok") tg.HapticFeedback.notificationOccurred("success");
      else tg.HapticFeedback.impactOccurred("light");
    } catch (e) { /* без вибрации */ }
  }
  function openLink(url) { if (!url) return; if (tg && tg.openLink) tg.openLink(url); else window.open(url, "_blank"); }
  function openTg(url) { if (!url) return; if (tg && tg.openTelegramLink) tg.openTelegramLink(url); else window.open(url, "_blank"); }

  var toastTimer;
  function toast(text) {
    var el = $("toast");
    el.textContent = text; el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 2600);
  }

  function post(path, body) {
    return fetch(path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ initData: initData() }, body || {}))
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (json) {
        if (!r.ok) { var err = new Error(json.error || (r.status === 401 ? "auth" : "http " + r.status)); err.status = r.status; throw err; }
        return json;
      });
    });
  }

  /* ---------- вкладки ---------- */
  var tabs = ["home", "devices", "plans", "profile"];
  function show(tab) {
    tabs.forEach(function (name) { $("tab-" + name).hidden = name !== tab; });
    document.querySelectorAll(".tabbar button").forEach(function (b) {
      if (b.dataset.tab === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    window.scrollTo(0, 0);
  }

  /* ---------- главная ---------- */
  function renderHome(s) {
    var a = s.access, status = $("status");
    status.className = "pill";
    $("renew").hidden = !a;
    $("traffic").hidden = true;
    if (!a) {
      $("days").textContent = days(s.trial.days);
      status.classList.add("is-warn");
      status.querySelector("b").textContent = "Бесплатно";
      $("plan-title").textContent = "Пробный период";
      $("plan-devices").textContent = "До " + s.trial.devices + " " + devicesWord(s.trial.devices) + " · " + s.trial.gb + " ГБ · без оплаты";
      $("main-cta").querySelector("span").textContent = "Попробовать бесплатно";
      return;
    }
    if (a.active) {
      // 2 дня 23 часа — это «3 дня»: сразу после выдачи пробника иначе показали бы «2 дня».
      var left = a.seconds_left || 0;
      $("days").textContent = left >= 86400 ? days(Math.round(left / 86400)) : Math.max(1, Math.round(left / 3600)) + " ч";
      status.classList.add("is-ok");
      status.querySelector("b").textContent = "Активна";
    } else {
      $("days").textContent = days(0);
      var limited = a.status === "limited";
      status.classList.add(limited ? "is-warn" : "is-bad");
      status.querySelector("b").textContent = limited ? "Трафик закончился" : a.status === "disabled" ? "Отключена" : "Истекла";
    }
    $("plan-title").textContent = a.limit_bytes > 0 ? "Пробный период" : "VPN · безлимитный";
    $("plan-devices").textContent = a.devices.length + " из " + a.device_limit + " " + devicesWord(a.device_limit);
    if (a.limit_bytes > 0) {
      $("traffic").hidden = false;
      var pct = Math.min(100, Math.round(100 * a.used_bytes / a.limit_bytes));
      $("traffic").querySelector(".meter__bar span").style.width = pct + "%";
      $("traffic-text").textContent = "Трафик: " + gb(a.used_bytes) + " из " + gb(a.limit_bytes) + " ГБ";
    }
    $("main-cta").querySelector("span").textContent = a.active ? "Добавить устройство" : "Продлить доступ";
    $("invite-text").textContent = "Друг получит " + days(s.trial.days) + " бесплатно";
  }

  /* ---------- устройства ---------- */
  function seenText(ts) {
    var d = Math.floor((Date.now() / 1000 - ts) / 86400);
    return d <= 0 ? "в сети сегодня" : d === 1 ? "был вчера" : "был " + days(d) + " назад";
  }
  function renderDevices(s) {
    var list = $("devices"), a = s.access;
    list.textContent = "";
    var limit = a ? a.device_limit : s.trial.devices;
    var items = a ? a.devices : [];
    $("devices-count").textContent = items.length + " из " + limit + " " + devicesWord(limit);
    if (!items.length) {
      var empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = a ? "Пока ни одного устройства — подключите первое." : "Сначала получите доступ — это бесплатно.";
      list.appendChild(empty);
    }
    items.forEach(function (d) {
      var li = document.createElement("li");
      var ico = document.createElement("span"); ico.className = "dev-ico";
      var desktop = /mac|windows|linux|ubuntu/i.test(d.os || "") && !/ios|ipad/i.test(d.os || "");
      ico.innerHTML = '<svg class="icon"><use href="#' + (desktop ? "i-laptop" : "i-phone") + '"/></svg>';
      var text = document.createElement("span");
      var b = document.createElement("b"); b.textContent = d.model;
      var small = document.createElement("small"); small.textContent = (d.os ? d.os + " · " : "") + seenText(d.last_seen);
      text.appendChild(b); text.appendChild(small);
      li.appendChild(ico); li.appendChild(text);
      list.appendChild(li);
    });
    $("devices-cta").querySelector("span").textContent = a ? "Добавить устройство" : "Попробовать бесплатно";
  }

  /* ---------- тарифы ---------- */
  function renderPlans(s) {
    var box = $("plans");
    box.textContent = "";
    var base = s.plans.length ? s.plans[0].per_month : 0;
    s.plans.forEach(function (p, i) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "plan" + (i === s.plans.length - 1 ? " plan--best" : "");
      var left = document.createElement("span");
      var b = document.createElement("b"); b.textContent = p.label;
      var small = document.createElement("small"); small.textContent = rub(p.per_month) + " в месяц";
      var save = base ? Math.round(100 - 100 * p.per_month / base) : 0;
      if (save > 0) { var em = document.createElement("span"); em.className = "plan__save"; em.textContent = "−" + save + "%"; small.appendChild(em); }
      left.appendChild(b); left.appendChild(small);
      var price = document.createElement("strong"); price.textContent = rub(p.price);
      btn.appendChild(left); btn.appendChild(price);
      if (i === s.plans.length - 1) {
        var badge = document.createElement("span"); badge.className = "plan__badge"; badge.textContent = "Выгоднее всего";
        btn.appendChild(badge);
      }
      btn.addEventListener("click", function () {
        haptic();
        toast("Оплата скоро будет подключена. Пока доступен пробный период — " + days(s.trial.days) + " бесплатно.");
      });
      box.appendChild(btn);
    });
  }

  /* ---------- профиль ---------- */
  function menuItem(label, action) {
    var li = document.createElement("li"), btn = document.createElement("button");
    btn.type = "button";
    var span = document.createElement("span"); span.textContent = label;
    btn.appendChild(span);
    btn.insertAdjacentHTML("beforeend", '<svg class="icon"><use href="#i-chev"/></svg>');
    btn.addEventListener("click", function () { haptic(); action(); });
    li.appendChild(btn);
    return li;
  }
  function renderProfile(s) {
    var u = s.user;
    $("profile-name").textContent = u.first_name || (u.username ? "@" + u.username : "Профиль");
    $("profile-id").textContent = (u.username ? "@" + u.username + " · " : "") + "ID " + u.id;
    $("avatar").textContent = (u.first_name || s.name || "E").trim().charAt(0).toUpperCase();
    var a = s.access;
    $("link-card").hidden = !(a && a.sub_url);
    if (a && a.sub_url) $("sub-url").textContent = a.sub_url;
    var menu = $("menu");
    menu.textContent = "";
    if (a && a.sub_url) menu.appendChild(menuItem("Подключить устройство", function () { openLink(a.sub_url); }));
    if (s.support_link) menu.appendChild(menuItem("Написать в поддержку", function () { openTg(s.support_link); }));
    if (s.docs && s.docs.tariffs) menu.appendChild(menuItem("Тарифы и оплата", function () { openLink(s.docs.tariffs); }));
    if (s.docs && s.docs.terms) menu.appendChild(menuItem("Пользовательское соглашение", function () { openLink(s.docs.terms); }));
    if (s.docs && s.docs.privacy) menu.appendChild(menuItem("Политика конфиденциальности", function () { openLink(s.docs.privacy); }));
    if (s.bot) menu.appendChild(menuItem("Открыть бота", function () { openTg("https://t.me/" + s.bot); }));
  }

  function render(s) {
    data = s;
    document.title = s.name;
    renderHome(s); renderDevices(s); renderPlans(s); renderProfile(s);
    $("loading").hidden = true; $("error").hidden = true;
    $("tabbar").hidden = false;
  }

  function fail(err) {
    $("loading").hidden = true;
    tabs.forEach(function (name) { $("tab-" + name).hidden = true; });
    $("tabbar").hidden = true;
    $("error").hidden = false;
    $("error-text").textContent = err && err.status === 401
      ? "Откройте приложение кнопкой «Открыть VPN» в Telegram-боте."
      : "Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.";
  }

  function load() {
    $("error").hidden = true; $("loading").hidden = false;
    return post("api/me").then(function (s) { render(s); show("home"); }).catch(fail);
  }

  /* ---------- действия ---------- */
  var busy = false;
  function takeTrial() {
    if (busy) return;
    busy = true;
    ["main-cta", "devices-cta"].forEach(function (id) { $(id).disabled = true; });
    post("api/trial").then(function (s) {
      render(s); show("home"); haptic("ok");
      toast(s.issued ? "Доступ открыт — подключите устройство" : "Доступ уже есть");
    }).catch(function (e) { toast(e.message && e.message !== "auth" ? e.message : "Не получилось — попробуйте ещё раз"); })
      .then(function () { busy = false; ["main-cta", "devices-cta"].forEach(function (id) { $(id).disabled = false; }); });
  }
  function mainAction() {
    haptic();
    if (!data) return;
    var a = data.access;
    if (!a) return takeTrial();
    if (!a.active) return show("plans");
    openLink(a.sub_url);
  }

  $("main-cta").addEventListener("click", mainAction);
  $("devices-cta").addEventListener("click", mainAction);
  $("renew").addEventListener("click", function () { haptic(); show("plans"); });
  $("retry").addEventListener("click", load);
  $("invite").addEventListener("click", function () {
    haptic();
    if (!data || !data.referral_link) return;
    var text = "Попробуй " + data.name + " — " + days(data.trial.days) + " бесплатно";
    openTg("https://t.me/share/url?url=" + encodeURIComponent(data.referral_link) + "&text=" + encodeURIComponent(text));
  });
  $("copy").addEventListener("click", function () {
    var url = data && data.access && data.access.sub_url;
    if (!url) return;
    haptic();
    (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(
      function () { toast("Ссылка скопирована"); },
      function () { toast("Нажмите и удерживайте ссылку, чтобы скопировать"); }
    );
  });
  document.querySelectorAll(".tabbar button").forEach(function (b) {
    b.addEventListener("click", function () { haptic(); show(b.dataset.tab); });
  });

  if (tg) {
    try {
      tg.ready(); tg.expand();
      if (tg.setHeaderColor) tg.setHeaderColor("#0F1A33");
      if (tg.setBackgroundColor) tg.setBackgroundColor("#0B1530");
      if (tg.setBottomBarColor) tg.setBottomBarColor("#0B1530");
      if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
    } catch (e) { /* старый клиент Telegram */ }
  }
  load();
})();
