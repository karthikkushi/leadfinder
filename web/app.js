(() => {
  const C = window.LF_CONFIG;
  const META = window.LF_META;
  const CAT = Object.fromEntries(META.categories.map((c) => [c.key, c.label]));
  const COUNTRY = Object.fromEntries(META.countries.map((c) => [c.code, c]));
  const PAGE = 30;
  const $ = (s, root = document) => root.querySelector(s);
  const store = {
    get(k, d = null) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
    del(k) { try { localStorage.removeItem(k); } catch { /* private mode */ } },
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : null);
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u || ""; } };
  const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const installed = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  // ---------- icons (inline SVG, no icon font) ----------
  const ICON = {
    flame: '<path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2 1-3.5 2-4.5.3 1.7 1.2 2.7 2.2 3C10.6 9 11 6 12 3z"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4zM7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4"/>',
    dots: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>',
    wa: '<path d="M3 21l1.6-4.7A8.5 8.5 0 1 1 8 19.6L3 21z"/><path d="M9 9.5c.3 2.2 2.3 4.4 4.8 5 .6.1 1.4-.4 1.6-1l-1.7-.9-.8.8c-1-.4-2-1.4-2.4-2.4l.8-.8-.8-1.7c-.7.1-1.2.6-1.5 1z"/>',
    more: '<circle cx="12" cy="5" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="12" cy="19" r="1.3"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    map: '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
  };
  const icon = (name, cls = "i") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICON[name] || ""}</svg>`;
  document.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = icon(el.dataset.icon); });
  $("#settings-btn").innerHTML = icon("gear");
  $("#install-close").innerHTML = icon("x");
  document.querySelectorAll(".icon-btn.close").forEach((el) => { el.innerHTML = icon("x"); });

  // ---------- state ----------
  const S = {
    code: null, me: null, tab: "today", country: store.get("lf_country", "IN"), summary: null,
    filters: { city: "", category: "", quality: store.get("lf_quality", "AB"), search: "" },
    results: "interested", byId: new Map(), pendingCall: null, items: [], offset: 0,
  };

  async function rpc(fn, args = {}) {
    let r;
    try {
      r = await fetch(`${C.supabaseUrl}/rest/v1/rpc/${fn}`, {
        method: "POST",
        headers: { apikey: C.supabaseKey, "Content-Type": "application/json" },
        body: JSON.stringify({ p_code: S.code, ...args }),
      });
    } catch {
      throw new Error("No internet connection. Check your network and try again.");
    }
    const data = await r.json().catch(() => null);
    if (!r.ok) {
      const msg = (data && data.message) || "";
      if (msg === "Invalid access code") { logout(true); throw new Error(msg); }
      if (/timeout/i.test(msg)) throw new Error("The server is busy. Please try again in a moment.");
      throw new Error(msg || `Something went wrong (${r.status})`);
    }
    return data;
  }

  let toastTimer;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 2800);
  }

  // ---------- login ----------
  async function start() {
    const fromLink = new URLSearchParams(location.hash.slice(1)).get("code");
    if (fromLink) {
      store.set("lf_code", fromLink);
      if (!isIOS) history.replaceState(null, "", location.pathname);
    }
    S.code = store.get("lf_code");
    if (!S.code) return showLogin();
    try {
      S.me = await rpc("app_login");
    } catch (e) {
      return showLogin(e.message);
    }
    $("#login").hidden = true;
    $("#app").hidden = false;
    document.body.classList.toggle("is-admin", S.me.role === "admin");
    if (!store.get("lf_name")) store.set("lf_name", S.me.name);
    showInstall();
    fillCountries();
    go(S.tab);
    refreshSummary();
  }
  function showLogin(error) {
    $("#app").hidden = true;
    $("#login").hidden = false;
    $("#login-error").hidden = !error;
    $("#login-error").textContent = error || "";
  }
  function logout(silent) {
    store.del("lf_code");
    S.code = null;
    if (!silent) location.reload();
  }
  window.addEventListener("hashchange", () => { if (location.hash.includes("code=")) start(); });
  $("#login-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const typed = $("#code-input").value.trim();
    store.set("lf_code", typed.includes("code=") ? typed.split("code=")[1].split(/[&\s]/)[0] : typed);
    start();
  });

  // ---------- country & summary ----------
  function fillCountries(list) {
    const codes = list && list.length ? list.map((c) => c.code) : ["IN"];
    if (!codes.includes(S.country)) codes.unshift(S.country);
    $("#country").innerHTML = codes.map((c) => `<option value="${c}">${esc(COUNTRY[c]?.name || c)}</option>`).join("");
    $("#country").value = S.country;
  }
  $("#country").addEventListener("change", () => {
    S.country = $("#country").value;
    store.set("lf_country", S.country);
    S.filters.city = "";
    refreshSummary().then(() => go(S.tab));
  });
  async function refreshSummary() {
    try {
      S.summary = await rpc("app_summary", { p_country: S.country });
      fillCountries(S.summary.countries);
      const due = S.summary.callbacks_due;
      $("#cb-badge").hidden = !due;
      $("#cb-badge").textContent = due;
      if (S.tab === "today") renderTodayHeader();
    } catch { /* header numbers are optional */ }
  }

  // ---------- navigation ----------
  $("#tabbar").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-tab]");
    if (b) go(b.dataset.tab);
  });
  function go(tab) {
    S.tab = tab;
    document.querySelectorAll("#tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    window.scrollTo({ top: 0 });
    ({ today: viewToday, all: viewAll, callbacks: viewCallbacks, results: viewResults, more: viewMore }[tab])();
  }
  const skeleton = (n = 3) => `<div class="list">${'<div class="skeleton"></div>'.repeat(n)}</div>`;
  const emptyBox = (title, text, ic = "inbox") => `<div class="empty">${icon(ic)}<b>${esc(title)}</b>${esc(text)}</div>`;
  const errorBox = (msg) => `<div class="empty">${icon("refresh")}<b>Couldn't load this</b>${esc(msg)}
      <div style="margin-top:12px"><button class="btn small" data-retry>Try again</button></div></div>`;
  $("#view").addEventListener("click", (e) => { if (e.target.closest("[data-retry]")) go(S.tab); });

  // ---------- Today ----------
  function renderTodayHeader() {
    const h = $("#today-hero");
    if (!h || !S.summary) return;
    const total = S.summary.hot_today || 0, done = S.summary.hot_done || 0;
    const pct = total ? Math.round((done / total) * 100) : 0;
    const d = new Date(`${S.summary.today}T12:00:00`);
    h.innerHTML = `
      <div class="date">${d.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</div>
      <h1>${icon("flame")}Today's hot leads</h1>
      <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${done}"><span style="width:${pct}%"></span></div>
      <div class="progress-label"><span>${done} of ${total} called</span><span>${total - done} to go</span></div>
      <div class="stats">
        <div class="stat"><b>${S.summary.calls_today}</b><span>calls today</span></div>
        <div class="stat"><b>${S.summary.callbacks_due}</b><span>callbacks due</span></div>
        <div class="stat"><b>${S.summary.won}</b><span>clients won</span></div>
      </div>`;
  }
  async function viewToday() {
    const v = $("#view");
    v.innerHTML = `<section class="hero" id="today-hero"><div class="skeleton" style="height:120px;border:0"></div></section>
      <div id="today-list">${skeleton(3)}</div><div id="earlier"></div>`;
    renderTodayHeader();
    try {
      const [today, earlier] = await Promise.all([
        rpc("app_list", { p_view: "today", p_country: S.country, p_limit: 50 }),
        rpc("app_list", { p_view: "earlier", p_country: S.country, p_limit: 20 }),
      ]);
      if (S.tab !== "today") return;
      remember(today); remember(earlier);
      $("#today-list").innerHTML = today.length
        ? `<div class="list">${today.map(card).join("")}</div>`
        : emptyBox("No hot leads yet today", "Fresh leads arrive every morning at about 9 AM. Meanwhile, open All leads.", "flame");
      $("#earlier").innerHTML = earlier.length ? `<div class="section-title"><h2>Still to call from earlier days</h2>
          <span>${earlier.length}${earlier.length === 20 ? "+" : ""}</span></div><div class="list">${earlier.map(card).join("")}</div>` : "";
    } catch (e) {
      $("#today-list").innerHTML = errorBox(e.message);
    }
  }

  // ---------- All leads ----------
  const QUALITY = [["A", "Best"], ["AB", "Best + good"], ["", "All"], ["nosite", "No website"], ["weaksite", "Website needs work"]];
  function viewAll() {
    const sum = S.summary?.summary;
    const cities = sum?.cities || [];
    const f = S.filters;
    $("#view").innerHTML = `
      <div class="searchbar">${icon("search")}<input id="f-search" type="search" placeholder="Search shop name, area or phone" value="${esc(f.search)}"></div>
      <div class="chips" id="f-quality">${QUALITY.map(([k, l]) => `<button class="chip ${f.quality === k ? "on" : ""}" data-q="${k}">${l}</button>`).join("")}</div>
      <div class="chips">
        <label class="chip"><span class="sr-only">City</span><select id="f-city"><option value="">All cities</option>
          ${cities.map((c) => `<option value="${esc(c.city)}" ${f.city === c.city ? "selected" : ""}>${esc(c.city)}</option>`).join("")}</select></label>
        <label class="chip"><span class="sr-only">Shop type</span><select id="f-category"><option value="">All shop types</option>
          ${META.categories.map((c) => `<option value="${c.key}" ${f.category === c.key ? "selected" : ""}>${esc(c.label)}</option>`).join("")}</select></label>
      </div>
      <div class="count-line" id="count-line">${sum ? `${Number(sum.tier_a + sum.tier_b).toLocaleString("en-IN")} best + good leads in ${esc(COUNTRY[S.country]?.name || S.country)}` : ""}</div>
      <div id="all-list">${skeleton(4)}</div>
      <div style="margin-top:12px"><button id="more-btn" class="btn ghost wide" hidden>Show more</button></div>`;
    let timer;
    $("#f-search").addEventListener("input", (e) => { clearTimeout(timer); timer = setTimeout(() => { f.search = e.target.value.trim(); loadAll(true); }, 350); });
    $("#f-quality").addEventListener("click", (e) => {
      const b = e.target.closest("[data-q]");
      if (!b) return;
      f.quality = b.dataset.q;
      store.set("lf_quality", f.quality);
      document.querySelectorAll("#f-quality .chip").forEach((c) => c.classList.toggle("on", c === b));
      loadAll(true);
    });
    $("#f-city").addEventListener("change", (e) => { f.city = e.target.value; loadAll(true); });
    $("#f-category").addEventListener("change", (e) => { f.category = e.target.value; loadAll(true); });
    $("#more-btn").addEventListener("click", () => loadAll(false));
    loadAll(true);
  }
  async function loadAll(reset) {
    if (reset) { S.items = []; S.offset = 0; $("#all-list").innerHTML = skeleton(4); }
    const f = S.filters;
    try {
      const rows = await rpc("app_list", {
        p_view: "all", p_country: S.country, p_city: f.city || null, p_category: f.category || null,
        p_quality: f.quality || null, p_search: f.search || null, p_limit: PAGE, p_offset: S.offset,
      });
      if (S.tab !== "all") return;
      remember(rows);
      S.items = S.items.concat(rows);
      S.offset += rows.length;
      $("#all-list").innerHTML = S.items.length ? `<div class="list">${S.items.map(card).join("")}</div>`
        : emptyBox("No leads match", "Try another city, shop type or filter.", "search");
      $("#more-btn").hidden = rows.length < PAGE;
    } catch (e) {
      $("#all-list").innerHTML = errorBox(e.message);
    }
  }

  // ---------- Callbacks & Results ----------
  async function simpleList(view, emptyTitle, emptyText, ic) {
    $("#view").innerHTML = `<div id="simple-list">${skeleton(3)}</div>`;
    try {
      const rows = await rpc("app_list", { p_view: view, p_country: S.country, p_limit: 100 });
      if (!["callbacks", "results"].includes(S.tab)) return;
      remember(rows);
      $("#simple-list").innerHTML = rows.length ? `<div class="list">${rows.map(card).join("")}</div>` : emptyBox(emptyTitle, emptyText, ic);
    } catch (e) {
      $("#simple-list").innerHTML = errorBox(e.message);
    }
  }
  function viewCallbacks() {
    simpleList("callbacks", "No callbacks", "When a shop says 'call me later', tap Callback and it shows up here.", "clock")
      .then(() => { $("#view").insertAdjacentHTML("afterbegin", `<div class="section-title"><h2>Callbacks</h2><span>soonest first</span></div>`); });
  }
  function viewResults() {
    const tabs = [["interested", "Interested"], ["won", "Won"], ["done", "Closed"]];
    const draw = () => {
      $("#view").innerHTML = `<div class="segmented">${tabs.map(([k, l]) => `<button data-r="${k}" class="${S.results === k ? "on" : ""}">${l}</button>`).join("")}</div><div id="res"></div>`;
      $(".segmented").addEventListener("click", (e) => { const b = e.target.closest("[data-r]"); if (b) { S.results = b.dataset.r; draw(); } });
      const empty = { interested: ["No interested shops yet", "Keep calling - the first yes is close."],
        won: ["No clients yet", "Mark a shop Won when they agree to a website."], done: ["Nothing closed yet", "Not interested, wrong numbers and shops with websites land here."] }[S.results];
      $("#res").innerHTML = skeleton(2);
      rpc("app_list", { p_view: S.results, p_country: S.country, p_limit: 100 }).then((rows) => {
        if (S.tab !== "results") return;
        remember(rows);
        $("#res").innerHTML = rows.length ? `<div class="list">${rows.map(card).join("")}</div>` : emptyBox(empty[0], empty[1], "trophy");
      }).catch((e) => { $("#res").innerHTML = errorBox(e.message); });
    };
    draw();
  }

  // ---------- cards ----------
  function remember(rows) { rows.forEach((l) => S.byId.set(l.id, l)); }
  const initials = (name) => (name || "?").replace(/^(dr\.?|sri|shri|the)\s+/i, "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  const placeNorm = (s) => (s || "").toLowerCase().replace("mysore", "mysuru").replace("bangalore", "bengaluru");
  function areaOf(l) {
    const a = l.locality || "";
    return !a || placeNorm(a) === placeNorm(l.city) ? l.city : `${a}, ${l.city}`;
  }
  function socialNames(l) {
    const names = [...new Set((l.socials || []).map((s) => host(s).split(".")[0]).filter(Boolean))];
    return names.map((n) => n.charAt(0).toUpperCase() + n.slice(1)).slice(0, 3);
  }
  function statusTag(l) {
    switch (l.website_status) {
      case "none": return ["No website", "nosite"];
      case "social_only": { const s = socialNames(l); return [s.length ? `Only ${s.slice(0, 2).join(" + ")}` : "Only social media", "nosite"]; }
      case "directory_only": return ["Only directory listings", "nosite"];
      case "dead": return ["Website not working", "nosite"];
      case "weak": return ["Website needs work", "weak"];
      default: return [l.priority === 1 ? "No website (not checked yet)" : "Website not checked yet", ""];
    }
  }
  const OUTCOME = { no_answer: "No answer", callback: "Callback", interested: "Interested", won: "Won", not_interested: "Not interested",
    wrong_number: "Wrong number", do_not_call: "Don't call", has_website: "Has website" };
  function whyList(l, n) {
    const why = (l.reasons || []).filter((r) => !/^(No website|Their website|Website needs|Checked:)/.test(r)).slice(0, n);
    return why.length ? `<ul class="why">${why.map((r) => `<li>${icon("check")}<span>${esc(r)}</span></li>`).join("")}</ul>` : "";
  }
  function card(l) {
    const [st, cls] = statusTag(l);
    const tier = { A: ["Best lead", "tA"], B: ["Good lead", "tB"] }[l.tier];
    const done = l.stage !== "new" || (l.call_count > 0 && S.tab === "today");
    const cb = l.stage === "callback" && l.callback_at
      ? `<span class="tag outcome">${icon("clock", "i")} ${esc(new Date(l.callback_at).toLocaleString("en-IN", { weekday: "short", hour: "numeric", minute: "2-digit" }))}</span>` : "";
    const last = l.last_outcome && l.stage !== "callback" ? `<span class="tag outcome">${esc(OUTCOME[l.last_outcome] || l.last_outcome)}</span>` : "";
    const digits = (l.phone_intl || "").replace(/\D/g, "");
    const kit = l.stage === "interested" && kitLink(l);
    return `
    <article class="card ${done && S.tab === "today" ? "done" : ""}" data-id="${l.id}">
      <div class="card-top" data-open>
        <div class="avatar" aria-hidden="true">${esc(initials(l.name))}</div>
        <div class="card-main">
          <h3>${esc(l.name)}</h3>
          <div class="meta">${esc(CAT[l.category] || l.category)} · ${esc(areaOf(l))}</div>
          <div class="tags">${tier ? `<span class="tag ${tier[1]}">${tier[0]}</span>` : ""}<span class="tag ${cls}">${esc(st)}</span>${cb}${last}</div>
        </div>
      </div>
      ${l.brief?.headline ? `<p class="brief-head">${esc(l.brief.headline)}</p>` : whyList(l, 2)}
      <div class="card-actions">
        <a class="btn call" href="tel:${esc(l.phone_intl || "")}" data-call>${icon("phone")}Call</a>
        ${kit ? `<a class="btn wa" target="_blank" rel="noopener" href="${esc(kit)}">${icon("wa")}Send sample</a>`
          : `<a class="btn wa" target="_blank" rel="noopener" href="https://wa.me/${digits}?text=${encodeURIComponent(waText(l))}">${icon("wa")}WhatsApp</a>`}
        <button class="btn more" data-open aria-label="Details and result">${icon("more")}</button>
      </div>
    </article>`;
  }
  $("#view").addEventListener("click", (e) => {
    const art = e.target.closest(".card");
    if (!art) return;
    const l = S.byId.get(art.dataset.id);
    if (e.target.closest("[data-call]")) { S.pendingCall = { id: l.id, at: Date.now() }; return; }
    if (e.target.closest("[data-open]")) openLead(l);
  });

  // after a call, coming back to the app asks how it went
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible" || !S.pendingCall) return;
    const p = S.pendingCall;
    S.pendingCall = null;
    if (Date.now() - p.at < 3 * 3600e3 && S.byId.has(p.id)) openLead(S.byId.get(p.id), true);
  });

  // ---------- script & messages ----------
  const SPOKEN = {
    dentist: "dentists", dermatologist: "skin clinics", physio: "physiotherapists", eye_clinic: "eye clinics and opticians",
    vet: "vets", pet_shop: "pet shops", clinic: "clinics", pharmacy: "medical stores", clothing: "clothing shops",
    jewellery: "jewellery shops", footwear: "footwear shops", mobile_electronics: "mobile and electronics shops",
    furniture_home: "furniture and home decor shops", hardware: "hardware shops", grocery: "grocery stores",
    bakery_sweets: "bakeries and sweet shops", gifts_books: "gift shops", sports: "sports shops", auto_parts: "auto parts shops",
    salon_beauty: "salons", gym_fitness: "gyms", restaurant_cafe: "restaurants and cafes", tuition: "classes and tuition centres",
    events_photo: "event services", laundry: "laundry services", general_shop: "shops",
    home_services: "plumbers, electricians and home services",
  };
  const PLAIN = [
    [/^Not mobile-friendly/, "it doesn't fit a phone screen"], [/^No HTTPS/, "browsers mark it 'Not secure'"],
    [/^Security certificate/, "browsers show a security warning"], [/^Looks outdated \(© (\d{4})\)/, "it looks like it was last updated in $1"],
    [/^Under construction/, "it still shows a 'coming soon' page"], [/^Very little content/, "there's very little information on it"],
    [/^Free website-builder/, "it's on a free website-builder address"], [/^Slow to load/, "it's slow to open"],
    [/^No tap-to-call/, "there's no button to call or WhatsApp you"], [/^No page title/, "it's hard to find on Google"],
    [/^Website not opening/, "it isn't opening right now"], [/^Website shows an error/, "it shows an error page"],
    [/^Domain parked|^Domain is up for sale/, "the web address has expired"],
    [/^Old Google business.site/, "it was on Google's free site service, which Google has shut down"],
  ];
  const plain = (issue) => { for (const [re, txt] of PLAIN) if (re.test(issue)) return issue.replace(re, txt).replace(/\s+-\s.*$|\s*\(.*$/, ""); return issue.toLowerCase(); };
  const listJoin = (a) => (a.length <= 1 ? a.join("") : `${a.slice(0, -1).join(", ")} and ${a[a.length - 1]}`);
  function script(l) {
    const who = store.get("lf_name") || "[your name]";
    const co = store.get("lf_company") || "[your company]";
    const price = store.get("lf_price");
    const type = SPOKEN[l.category] || "shops like yours";
    const area = l.locality && l.locality !== l.city ? l.locality : l.city;
    const rival = (l.reasons || []).find((r) => /similar shops nearby have websites/.test(r));
    let body;
    if (l.priority === 1 && l.website_status !== "dead") {
      const s = socialNames(l);
      const only = l.website_status === "social_only" && s.length ? ` - only your ${s.join(" and ")} page${s.length > 1 ? "s" : ""}` : "";
      body = `I was looking for ${type} in ${area} online and couldn't find a website for ${l.name}${only}.` +
        (rival ? ` ${rival.replace(/^(\d+) of (\d+) similar shops nearby/, "$1 of the $2 similar shops near you already")} - customers who search on Google find them first.` : " Most customers search on Google before they visit.") +
        `\n\nWe make simple, fast websites for local businesses: your photos, timings, location, and Call and WhatsApp buttons${price ? ` - ${price}` : ""}. I can make a free sample for you first. Can I send it on WhatsApp?`;
    } else if (l.website_status === "dead") {
      body = `I tried to open your website${l.website ? ` (${host(l.website)})` : ""} and ${plain((l.issues || [])[0] || "Website not opening")}, so customers who look you up hit a dead end.\n\nWe can put up a new, fast website quickly${price ? ` - ${price}` : ""}. Can I send you a free sample on WhatsApp?`;
    } else {
      const probs = (l.issues || []).filter((i) => !/^No tap-to-call/.test(i) || l.issues.length === 1).slice(0, 3).map(plain);
      body = `I had a look at your website${l.website ? ` (${host(l.website)})` : ""}. On a phone, ${listJoin(probs) || "it could work much better"}.\n\nWe redesign websites for local businesses so they load fast, look great on phones and have Call and WhatsApp buttons${price ? ` - ${price}` : ""}. Can I send you a free sample of how yours could look?`;
    }
    return `Hello, am I speaking with ${l.name}? This is ${who} from ${co}.\n\n${body}\n\nIf they're busy: "When is a good time to call back?" (tap Callback)`;
  }
  const fill = (t) => String(t || "").replaceAll("{me}", store.get("lf_name") || "[your name]").replaceAll("{company}", store.get("lf_company") || "[your company]");
  const cite = (t) => esc(fill(t)).replace(/\s*\[F\d+\](\[F\d+\])*/g, "");
  function waText(l) {
    if (l.brief?.whatsapp) return fill(l.brief.whatsapp);
    const who = store.get("lf_name") || "";
    const co = store.get("lf_company") || "";
    const sample = store.get("lf_sample");
    return `Hi, this is ${who}${co ? ` from ${co}` : ""}. We make websites for local businesses like ${l.name}.` +
      (sample ? ` Here is a sample of what we can build for you: ${sample}` : " Can I send you a free sample of what your website could look like?");
  }

  // Shop types with a Kalvio Build sample website (kalvio-build repo, docs/DEMO_LINKS.md).
  const SAMPLE_KEYS = new Set(["dentist", "dermatologist", "clinic", "physio", "eye_clinic", "vet", "pet_shop", "salon_beauty",
    "gym_fitness", "jewellery", "clothing", "furniture_home", "events_photo", "tuition", "restaurant_cafe", "bakery_sweets", "home_services"]);
  /** Kalvio Build's WhatsApp kit for this shop: opens with the sample link, both messages, a picture and a video ready. */
  function kitLink(l) {
    if (!SAMPLE_KEYS.has(l.category) || !S.code) return null;
    const q = new URLSearchParams({ key: l.category, name: l.name });
    if (l.locality && placeNorm(l.locality) !== placeNorm(l.city)) q.set("area", l.locality);
    else if (l.address) q.set("address", l.address); // the kit picks the area out of the address
    if (l.city) q.set("city", l.city);
    if (l.phone_intl) q.set("phone", l.phone_intl);
    // The code rides in the #hash, which browsers never send to a server; the kit needs it to take the picture.
    return `https://kalvio-build.pages.dev/share?${q}#code=${encodeURIComponent(S.code)}`;
  }

  // ---------- lead sheet ----------
  const pad = (n) => String(n).padStart(2, "0");
  const localValue = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const at = (days, hour) => { const d = new Date(); d.setDate(d.getDate() + days); d.setHours(hour, 0, 0, 0); return d; };
  function briefHtml(b, closed) {
    const li = (a) => (a || []).map((x) => `<li>${cite(x)}</li>`).join("");
    return `<details class="box brief" ${closed ? "" : "open"}><summary><b>Sales brief</b></summary>
      <p class="brief-head">${cite(b.headline)}</p>
      <h4>Why call</h4><ul>${li(b.why_call)}</ul>
      <h4>Sell</h4><p><b>${cite(b.sell?.main)}</b>${b.sell?.add_on ? ` + ${cite(b.sell.add_on)}` : ""}</p>
      <h4>Say first</h4><p class="script">${cite(b.opening)}</p>
      <h4>Ask</h4><ol>${li(b.questions)}</ol>
      <h4>Pitch</h4><p class="script">${cite(b.pitch)}</p>
      <h4>If they say…</h4>${(b.objections || []).map((o) => `<p><b>“${cite(o.they_say)}”</b><br>${cite(o.you_say)}</p>`).join("")}
      <h4>Don't say</h4><ul>${li(b.dont_say)}</ul>
      <h4>Free sample should show</h4><p>${cite(b.sample)}</p>
      <h4>Follow up</h4><p>${cite(b.follow_up)}</p>
      <details><summary class="muted small">Facts behind this brief</summary><ul class="muted small">${li(b.facts)}</ul></details>
    </details>`;
  }
  function openLead(l, askResult = false) {
    const [st, cls] = statusTag(l);
    const digits = (l.phone_intl || "").replace(/\D/g, "");
    const kit = kitLink(l);
    const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${l.name} ${l.locality || ""} ${l.city}`)}`;
    const site = safeUrl(l.website) || safeUrl((l.socials || [])[0]);
    const siteLabel = safeUrl(l.website) ? host(l.website) : site ? socialNames(l)[0] || "Page" : null;
    const open = ["new", "callback", "interested"].includes(l.stage);
    const issues = (l.issues || []).length ? `<div class="box"><h4>Website problems</h4><ul>${l.issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div>` : "";
    $("#sheet-body").innerHTML = `
      <div class="grabber"></div>
      <div class="detail">
        <div class="sheet-head"><h2>${esc(l.name)}</h2><button class="icon-btn" data-close aria-label="Close">${icon("x")}</button></div>
        <div class="meta" style="margin-top:-8px">${esc(CAT[l.category] || l.category)} · ${esc(areaOf(l))}</div>
        ${askResult ? `<div class="ask">How did the call go? Tap a result below.</div>` : ""}
        <div class="tags" style="margin:0">${l.tier === "A" ? '<span class="tag tA">Best lead</span>' : l.tier === "B" ? '<span class="tag tB">Good lead</span>' : ""}<span class="tag ${cls}">${esc(st)}</span></div>
        <div class="phone-big">${esc(l.phone || "")}</div>
        <div class="row">
          <a class="btn call" href="tel:${esc(l.phone_intl || "")}" data-call-sheet>${icon("phone")}Call</a>
          <a class="btn wa" target="_blank" rel="noopener" href="https://wa.me/${digits}?text=${encodeURIComponent(waText(l))}">${icon("wa")}WhatsApp</a>
        </div>
        ${kit ? `<a class="btn sample wide" target="_blank" rel="noopener" href="${esc(kit)}">${icon("wa")}<span>Send sample<small>Link, messages, picture and video, ready in one tap</small></span></a>` : ""}
        <div class="links">
          <a class="btn small ghost" target="_blank" rel="noopener" href="${esc(maps)}">${icon("map")}Map</a>
          ${site ? `<a class="btn small ghost" target="_blank" rel="noopener" href="${esc(site)}">${icon("globe")}${esc(siteLabel)}</a>` : ""}
        </div>
        ${(l.reasons || []).length ? `<div class="box"><h4>Why call</h4>${whyList(l, 6).replace('class="why"', 'class="why" style="margin:0"')}</div>` : ""}
        ${issues}
        ${l.brief?.opening ? briefHtml(l.brief, askResult) : `<details class="box" ${askResult ? "" : "open"}><summary><b>What to say</b></summary><p class="script">${esc(script(l))}</p></details>`}
        <label>Notes<textarea id="note" placeholder="Owner's name, best time to call, price they asked…">${esc(l.notes || "")}</textarea></label>
        ${open ? `<div><h4 class="muted small" style="margin:0 0 8px">Result of the call</h4>
          <div class="outcomes">
            <button data-o="no_answer" class="quiet">No answer</button>
            <button data-o="callback">${icon("clock")}Callback</button>
            <button data-o="interested" class="good">Interested</button>
            <button data-o="won" class="good">${icon("trophy")}Won</button>
            <button data-o="not_interested" class="quiet">Not interested</button>
            <button data-o="has_website" class="quiet">Has website</button>
            <button data-o="wrong_number" class="quiet">Wrong number</button>
            <button data-o="do_not_call" class="quiet">Don't call</button>
          </div>
          <div class="cb-row" id="cb-row" hidden>
            <label>Call back on<input id="cb-when" type="datetime-local"></label>
            <div class="chips" id="cb-quick"></div>
            <button class="btn primary wide" id="cb-save">Save callback</button>
          </div></div>`
          : `<button class="btn ghost wide" data-o="reopen">Move back to Today / All leads</button>`}
        <button class="btn ghost wide" data-o="note">Save note only</button>
      </div>`;
    const sheet = $("#sheet");
    sheet.onclick = async (e) => {
      if (e.target === sheet || e.target.closest("[data-close]")) return sheet.close();
      if (e.target.closest("[data-call-sheet]")) { S.pendingCall = { id: l.id, at: Date.now() }; return; }
      const b = e.target.closest("[data-o]");
      if (b) {
        if (b.dataset.o === "callback") return showCallback();
        await record(l, b.dataset.o);
      }
      if (e.target.closest("#cb-save")) {
        const v = $("#cb-when").value;
        if (!v) return toast("Pick a day and time");
        await record(l, "callback", new Date(v).toISOString());
      }
    };
    if (!sheet.open) sheet.showModal();
    sheet.scrollTop = 0;
  }
  function showCallback() {
    $("#cb-row").hidden = false;
    $("#cb-when").value = localValue(at(1, 11));
    const monday = at(((8 - new Date().getDay()) % 7) || 7, 11);
    const quick = [["In 2 hours", new Date(Date.now() + 2 * 3600e3)], ["Tomorrow 11 AM", at(1, 11)], ["Tomorrow 5 PM", at(1, 17)], ["Monday 11 AM", monday]];
    $("#cb-quick").innerHTML = quick.map(([t], i) => `<button type="button" class="chip" data-i="${i}">${t}</button>`).join("");
    $("#cb-quick").onclick = (ev) => { const q = ev.target.closest("[data-i]"); if (q) $("#cb-when").value = localValue(quick[q.dataset.i][1]); };
    $("#cb-row").scrollIntoView({ behavior: "smooth", block: "center" });
  }
  async function record(l, outcome, callbackAt) {
    const note = $("#note")?.value || null;
    const buttons = document.querySelectorAll("#sheet button");
    buttons.forEach((b) => { b.disabled = true; });
    try {
      await rpc("app_update_lead", { p_id: l.id, p_outcome: outcome, p_note: note, p_callback_at: callbackAt || null });
      const labels = { no_answer: "Saved: no answer", callback: "Callback saved", interested: "Interested - great! 🎉", won: "Client won! 🎉",
        not_interested: "Marked not interested", has_website: "Removed - they have a website", wrong_number: "Marked wrong number",
        do_not_call: "Won't be called again", reopen: "Moved back to the call list", note: "Note saved" };
      toast(labels[outcome] || "Saved");
      $("#sheet").close();
      refreshSummary();
      go(S.tab);
    } catch (e) {
      toast(e.message);
      buttons.forEach((b) => { b.disabled = false; });
    }
  }

  // ---------- More: admin + help ----------
  function viewMore() {
    const admin = S.me?.role === "admin";
    const sum = S.summary?.summary;
    $("#view").innerHTML = `
      ${admin ? `<div class="panel"><h2>Cities</h2>
        <p class="muted small">Counts refresh every 30 minutes${S.summary?.summary_at ? ` (last ${esc(new Date(S.summary.summary_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }))})` : ""}.</p>
        <div class="table-wrap">${sum ? `<table><tr><th>City</th><th class="num">Best</th><th class="num">Good</th><th class="num">No site</th><th class="num">Won</th></tr>
          ${sum.cities.map((c) => `<tr><td>${esc(c.city)}</td><td class="num">${c.a}</td><td class="num">${c.b}</td><td class="num">${c.p1}</td><td class="num">${c.won}</td></tr>`).join("")}</table>` : "No data yet."}</div></div>
      <div class="panel"><h2>Search a new city</h2>
        <p class="muted small">The agents scan it on their next run.</p>
        <form id="queue-form" class="stack" style="margin-top:10px">
          <select id="q-country">${META.countries.map((c) => `<option value="${c.code}" ${c.code === S.country ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>
          <input id="q-city" list="city-list" placeholder="City, e.g. Mangaluru" required><datalist id="city-list"></datalist>
          <select id="q-category"><option value="all">All shop types</option>${META.categories.map((c) => `<option value="${c.key}">${esc(c.label)}</option>`).join("")}</select>
          <button class="btn primary" type="submit">Add search</button>
        </form></div>
      <div class="panel"><h2>Searches</h2><div id="jobs">${skeleton(1)}</div></div>
      <div class="panel"><h2>Team</h2>
        <form id="member-form" class="stack" style="margin-top:10px">
          <input id="m-name" placeholder="Name of the new caller" required>
          <select id="m-role"><option value="caller">Caller</option><option value="admin">Admin</option></select>
          <button class="btn primary" type="submit">Create login link</button>
        </form>
        <div id="member-link" class="share" hidden></div>
        <div id="members" style="margin-top:8px"></div></div>` : ""}
      <div class="panel"><h2>Tips</h2><ul class="muted" style="margin:6px 0 0;padding-left:18px">
        <li>Call between 11 AM-1 PM or 4-7 PM, when owners are free.</li>
        <li>After every call, tap a result. It teaches the app which shops say yes.</li>
        <li>Fill in your name and company in Settings so the script and WhatsApp message use them.</li></ul></div>
      <p class="foot">Business data: Overture Maps Foundation, © OpenStreetMap contributors.</p>`;
    if (!admin) return;
    const fillCities = () => { const c = COUNTRY[$("#q-country").value]; $("#city-list").innerHTML = (c ? c.cities : []).map((x) => `<option value="${esc(x)}">`).join(""); };
    $("#q-country").addEventListener("change", fillCities);
    fillCities();
    $("#queue-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await rpc("app_queue_job", { p_country: $("#q-country").value, p_city: $("#q-city").value.trim(), p_category: $("#q-category").value });
        toast(`Added ${$("#q-city").value.trim()}`);
        $("#q-city").value = "";
        loadJobs();
      } catch (err) { toast(err.message); }
    });
    $("#member-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const name = $("#m-name").value.trim();
        const res = await rpc("app_add_member", { p_name: name, p_role: $("#m-role").value });
        const link = `${location.origin}${location.pathname}#code=${res.code}`;
        const msg = `Hi ${name}! Here's your Lead Finder app. Open it on your phone and tap Install:\n${link}`;
        const box = $("#member-link");
        box.hidden = false;
        box.innerHTML = `<b>${esc(name)}'s login link</b> (shown once - send it now):<br>${esc(link)}
          <div class="row" style="margin-top:10px"><button class="btn small" id="copy-link">Copy</button>
          <a class="btn small wa" target="_blank" rel="noopener" href="https://wa.me/?text=${encodeURIComponent(msg)}">Send on WhatsApp</a></div>`;
        $("#copy-link").onclick = () => navigator.clipboard.writeText(link).then(() => toast("Copied"));
        $("#m-name").value = "";
        loadMembers();
      } catch (err) { toast(err.message); }
    });
    $("#members").addEventListener("click", async (e) => {
      const b = e.target.closest("button[data-m]");
      if (!b) return;
      try { await rpc("app_set_member_active", { p_id: b.dataset.m, p_active: b.dataset.a === "true" }); loadMembers(); } catch (err) { toast(err.message); }
    });
    loadJobs();
    loadMembers();
  }
  async function loadJobs() {
    try {
      const jobs = await rpc("app_jobs");
      $("#jobs").innerHTML = jobs.length ? jobs.slice(0, 12).map((j) => `<div class="job"><span class="st ${j.status}">${j.status}</span> · <b>${esc(j.city)}</b>, ${esc(COUNTRY[j.country]?.name || j.country)}
        <div class="muted small" style="margin-top:4px">${esc(j.message || (j.status === "queued" ? "Starts with the next run" : ""))}</div></div>`).join("") : '<p class="muted">No searches yet.</p>';
    } catch (e) { $("#jobs").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
  }
  async function loadMembers() {
    try {
      const members = await rpc("app_members");
      $("#members").innerHTML = members.map((m) => `<div class="member"><div><b>${esc(m.name)}</b><div class="muted small">${m.role} · ${m.calls} calls · ${m.won} won</div></div>
        ${m.id === S.me.id ? '<span class="muted small">you</span>' : `<button class="btn small ghost" data-m="${m.id}" data-a="${!m.active}">${m.active ? "Switch off" : "Switch on"}</button>`}</div>`).join("");
    } catch (e) { $("#members").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
  }

  // ---------- settings ----------
  $("#settings-btn").addEventListener("click", () => {
    $("#s-name").value = store.get("lf_name", "");
    $("#s-company").value = store.get("lf_company", "");
    $("#s-price").value = store.get("lf_price", "");
    $("#s-sample").value = store.get("lf_sample", "");
    $("#settings").showModal();
  });
  $("#settings").addEventListener("click", (e) => { if (e.target === $("#settings")) $("#settings").close(); });
  $("#settings").addEventListener("close", () => {
    if ($("#settings").returnValue !== "save") return;
    store.set("lf_name", $("#s-name").value.trim());
    store.set("lf_company", $("#s-company").value.trim());
    store.set("lf_price", $("#s-price").value.trim());
    store.set("lf_sample", $("#s-sample").value.trim());
    toast("Saved");
    go(S.tab);
  });
  $("#logout-btn").addEventListener("click", () => logout(false));

  // ---------- install on the home screen ----------
  let installPrompt = null;
  function showInstall() {
    if (installed() || store.get("lf_install_hidden") || $("#app").hidden) return;
    if (installPrompt) {
      $("#install-text").textContent = "Add Lead Finder to your home screen";
      $("#install-btn").hidden = false;
    } else if (isIOS) {
      $("#install-text").textContent = "To install: tap Share, then 'Add to Home Screen'";
      $("#install-btn").hidden = true;
    } else return;
    $("#install").hidden = false;
  }
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); installPrompt = e; showInstall(); });
  window.addEventListener("appinstalled", () => { $("#install").hidden = true; toast("Installed - open Lead Finder from your home screen"); });
  $("#install-btn").addEventListener("click", async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    await installPrompt.userChoice;
    installPrompt = null;
    $("#install").hidden = true;
  });
  $("#install-close").addEventListener("click", () => { $("#install").hidden = true; store.set("lf_install_hidden", "1"); });
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});

  start();
})();
