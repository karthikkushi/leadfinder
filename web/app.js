(() => {
  const C = window.LF_CONFIG;
  const META = window.LF_META;
  const CAT = Object.fromEntries(META.categories.map((c) => [c.key, c.label]));
  const COUNTRY = Object.fromEntries(META.countries.map((c) => [c.code, c]));
  const PAGE = 30;
  const $ = (s) => document.querySelector(s);
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
  let installPrompt = null;

  let code = null;
  let me = null;
  let view = "to_call";
  let offset = 0;
  let leads = [];

  async function rpc(fn, args = {}) {
    const r = await fetch(`${C.supabaseUrl}/rest/v1/rpc/${fn}`, {
      method: "POST",
      headers: { apikey: C.supabaseKey, "Content-Type": "application/json" },
      body: JSON.stringify({ p_code: code, ...args }),
    });
    const data = await r.json().catch(() => null);
    if (!r.ok) {
      const msg = (data && data.message) || `Something went wrong (${r.status})`;
      if (msg === "Invalid access code") logout(true);
      throw new Error(msg);
    }
    return data;
  }

  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { t.hidden = true; }, 2600);
  }

  // ---------- login ----------
  async function start() {
    const fromLink = new URLSearchParams(location.hash.slice(1)).get("code");
    if (fromLink) {
      store.set("lf_code", fromLink);
      // iPhone home-screen apps don't share the browser's memory, so there the code stays in the address
      if (!isIOS) history.replaceState(null, "", location.pathname);
    }
    code = store.get("lf_code");
    if (!code) return showLogin();
    try {
      me = await rpc("app_login");
    } catch (e) {
      return showLogin(e.message);
    }
    $("#login").hidden = true;
    $("#app").hidden = false;
    document.body.classList.toggle("is-admin", me.role === "admin");
    if (!store.get("lf_name")) store.set("lf_name", me.name);
    fillStaticSelects();
    showInstall();
    await Promise.all([loadStats(), loadOptions()]);
    loadLeads(true);
  }

  function showLogin(error) {
    $("#app").hidden = true;
    $("#login").hidden = false;
    $("#login-error").hidden = !error;
    $("#login-error").textContent = error || "";
  }

  function logout(silent) {
    store.del("lf_code");
    code = null;
    if (!silent) location.reload();
  }

  window.addEventListener("hashchange", () => { if (location.hash.includes("code=")) start(); });

  // ---------- install on the home screen ----------
  function showInstall() {
    if (installed() || store.get("lf_install_hidden") || $("#app").hidden) return;
    if (installPrompt) {
      $("#install-text").textContent = "Add Lead Finder to your home screen";
      $("#install-btn").hidden = false;
    } else if (isIOS) {
      $("#install-text").textContent = "To install: tap Share, then 'Add to Home Screen'";
      $("#install-btn").hidden = true;
    } else {
      return;
    }
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

  $("#login-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const typed = $("#code-input").value.trim();
    store.set("lf_code", typed.includes("code=") ? typed.split("code=")[1].split(/[&\s]/)[0] : typed);
    start();
  });

  // ---------- stats & filters ----------
  async function loadStats() {
    const s = await rpc("app_stats");
    $("#stats").innerHTML = [
      [s.to_call, "to call"],
      [s.no_website, "no website"],
      [s.callbacks_due, "callbacks due"],
      [s.calls_today, "calls today"],
    ].map(([n, l]) => `<div class="stat"><b>${Number(n).toLocaleString("en-IN")}</b><span>${l}</span></div>`).join("");
    return s;
  }

  let options = { places: [], categories: [] };

  function fillPlaces() {
    const country = $("#f-country").value;
    const place = $("#f-place");
    const keep = place.value;
    place.innerHTML = `<option value="">All cities</option>` + options.places
      .filter((p) => !country || p.country === country)
      .map((p) => `<option value="${esc(p.country)}|${esc(p.city)}">${esc(p.city)} (${p.n})</option>`).join("");
    place.value = [...place.options].some((o) => o.value === keep) ? keep : "";
  }

  async function loadOptions() {
    const o = await rpc("app_options");
    options = o;
    const countries = [...new Set(o.places.map((p) => p.country))];
    if (!countries.includes("IN")) countries.unshift("IN");
    const saved = store.get("lf_country", "IN");
    $("#f-country").innerHTML = countries.map((c) => `<option value="${c}">${esc(COUNTRY[c]?.name || c)}</option>`).join("") +
      `<option value="">All countries</option>`;
    $("#f-country").value = countries.includes(saved) || saved === "" ? saved : "IN";
    fillPlaces();
    const cat = $("#f-category");
    const keepCat = cat.value;
    cat.innerHTML = `<option value="">All shop types</option>` + META.categories
      .filter((c) => o.categories.includes(c.key))
      .map((c) => `<option value="${c.key}">${esc(c.label)}</option>`).join("");
    cat.value = keepCat;
  }

  function fillStaticSelects() {
    $("#q-country").innerHTML = META.countries.map((c) => `<option value="${c.code}">${esc(c.name)}</option>`).join("");
    $("#q-category").innerHTML = `<option value="all">All shop types</option>` +
      META.categories.map((c) => `<option value="${c.key}">${esc(c.label)}</option>`).join("");
    fillCities();
  }
  function fillCities() {
    const c = COUNTRY[$("#q-country").value];
    $("#city-list").innerHTML = (c ? c.cities : []).map((x) => `<option value="${esc(x)}">`).join("");
  }
  $("#q-country").addEventListener("change", fillCities);

  $("#f-country").addEventListener("change", () => { store.set("lf_country", $("#f-country").value); fillPlaces(); loadLeads(true); });
  ["#f-place", "#f-category", "#f-priority"].forEach((s) => $(s).addEventListener("change", () => loadLeads(true)));
  let searchTimer;
  $("#f-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => loadLeads(true), 350); });

  // ---------- tabs ----------
  $("#tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-view]");
    if (!b) return;
    view = b.dataset.view;
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("active", x === b));
    $("#leads-view").hidden = view === "admin" || view === "team";
    $("#admin-view").hidden = view !== "admin";
    $("#team-view").hidden = view !== "team";
    if (view === "admin") loadAdmin();
    else if (view === "team") loadTeam();
    else loadLeads(true);
  });

  // ---------- leads ----------
  async function loadLeads(reset) {
    if (reset) { offset = 0; leads = []; }
    const [placeCountry, city] = ($("#f-place").value || "|").split("|");
    const country = placeCountry || $("#f-country").value;
    const list = $("#lead-list");
    if (reset) list.innerHTML = `<div class="empty">Loading…</div>`;
    let rows;
    try {
      rows = await rpc("app_leads", {
        p_view: view, p_country: country || null, p_city: city || null,
        p_category: $("#f-category").value || null,
        p_priority: $("#f-priority").value ? Number($("#f-priority").value) : null,
        p_search: $("#f-search").value.trim() || null, p_limit: PAGE, p_offset: offset,
      });
    } catch (e) {
      list.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
      return;
    }
    leads = leads.concat(rows);
    offset += rows.length;
    if (!leads.length) {
      const empty = { to_call: "Nothing to call right now. New leads arrive every morning.", callbacks: "No callbacks scheduled.",
        interested: "No interested shops yet - keep calling!", won: "No clients yet. The first one is close!", done: "Nothing here yet." };
      list.innerHTML = `<div class="empty">${empty[view] || "Nothing here."}</div>`;
    } else {
      list.innerHTML = leads.map(card).join("");
    }
    $("#more-btn").hidden = rows.length < PAGE;
  }
  $("#more-btn").addEventListener("click", () => loadLeads(false));

  function areaOf(l) {
    const a = l.locality || "";
    const norm = (s) => s.toLowerCase().replace("mysore", "mysuru").replace("bangalore", "bengaluru");
    const place = !a || norm(a) === norm(l.city) ? l.city : `${a}, ${l.city}`;
    return l.country === "IN" ? place : `${place}, ${COUNTRY[l.country]?.name || l.country}`;
  }

  function socialNames(l) {
    const names = [...new Set((l.socials || []).map((s) => host(s).split(".")[0]).filter(Boolean))];
    return names.map((n) => n.charAt(0).toUpperCase() + n.slice(1)).slice(0, 3);
  }

  function statusText(l) {
    switch (l.website_status) {
      case "none": return "No website";
      case "social_only": { const s = socialNames(l); return s.length ? `No website - only ${s.join(", ")}` : "No website - only social media"; }
      case "directory_only": return "No website - only directory listings";
      case "dead": return "Website not working";
      case "weak": return "Website needs work";
      case "good": return "Has a good website";
      default: return l.priority === 1 ? "No website (not yet double-checked)" : "Website not checked yet";
    }
  }

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
    [/^Not mobile-friendly/, "it doesn't fit a phone screen"],
    [/^No HTTPS/, "browsers mark it 'Not secure'"],
    [/^Security certificate/, "browsers show a security warning"],
    [/^Looks outdated \(© (\d{4})\)/, "it looks like it was last updated in $1"],
    [/^Under construction/, "it still shows a 'coming soon' page"],
    [/^Very little content/, "there's very little information on it"],
    [/^Free website-builder/, "it's on a free website-builder address"],
    [/^Slow to load/, "it's slow to open"],
    [/^No tap-to-call/, "there's no button to call or WhatsApp you"],
    [/^No page title/, "it's hard to find on Google"],
    [/^Website not opening/, "it isn't opening right now"],
    [/^Website shows an error/, "it shows an error page"],
    [/^Domain parked|^Domain is up for sale/, "the web address has expired"],
    [/^Old Google business.site/, "it was on Google's free site service, which Google has shut down"],
  ];
  const plain = (issue) => { for (const [re, txt] of PLAIN) if (re.test(issue)) return issue.replace(re, txt).replace(/\s*\(.*$/, ""); return issue.toLowerCase(); };
  const listJoin = (a) => (a.length <= 1 ? a.join("") : `${a.slice(0, -1).join(", ")} and ${a[a.length - 1]}`);

  function script(l) {
    const who = store.get("lf_name") || "[your name]";
    const co = store.get("lf_company") || "[your company]";
    const price = store.get("lf_price");
    const type = SPOKEN[l.category] || "shops like yours";
    const area = l.locality && l.locality !== l.city ? l.locality : l.city;
    const intro = `Hello, am I speaking with ${l.name}? This is ${who} from ${co}.`;
    let body;
    if (l.priority === 1 && l.website_status !== "dead") {
      const s = socialNames(l);
      const only = l.website_status === "social_only" && s.length ? ` - only your ${s.join(" and ")} page${s.length > 1 ? "s" : ""}` : "";
      body = `I was looking for ${type} in ${area} online and couldn't find a website for ${l.name}${only}. ` +
        `Most customers search on Google before they visit, and they choose the shops they can see.\n\n` +
        `We make simple, fast websites for local businesses: your photos, timings, location, and Call and WhatsApp buttons${price ? ` - ${price}` : ""}. ` +
        `I can make a free sample design for you first. Can I send it on WhatsApp?`;
    } else if (l.website_status === "dead") {
      body = `I tried to open your website${l.website ? ` (${host(l.website)})` : ""} and ${plain((l.issues || [])[0] || "Website not opening")}, ` +
        `so customers who look you up hit a dead end.\n\nWe can put up a new, fast website quickly${price ? ` - ${price}` : ""}. ` +
        `Can I send you a free sample design on WhatsApp?`;
    } else {
      const probs = (l.issues || []).filter((i) => !/^No tap-to-call/.test(i) || l.issues.length === 1).slice(0, 3).map(plain);
      body = `I had a look at your website${l.website ? ` (${host(l.website)})` : ""}. On a phone, ${listJoin(probs) || "it could work much better"}.\n\n` +
        `We redesign websites for local businesses so they load fast, look great on phones and have Call and WhatsApp buttons${price ? ` - ${price}` : ""}. ` +
        `Can I send you a free sample of how yours could look?`;
    }
    return `${intro}\n\n${body}\n\nIf they're busy: "When is a good time to call back?" (tap Callback)`;
  }

  function whatsappText(l) {
    const who = store.get("lf_name") || "";
    const co = store.get("lf_company") || "";
    return `Hi, this is ${who}${co ? ` from ${co}` : ""}. We make websites for local businesses like ${l.name}. ` +
      `Here is a free sample of what we can build for you:`;
  }

  function card(l) {
    const digits = (l.phone_intl || "").replace(/\D/g, "");
    const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${l.name} ${l.locality || ""} ${l.city}`)}`;
    const site = safeUrl(l.website) || safeUrl((l.socials || [])[0]);
    const siteLabel = safeUrl(l.website) ? "Website" : site ? socialNames(l)[0] || "Page" : "Website";
    const pillClass = ["new", "callback"].includes(l.stage) ? (l.priority === 1 ? "p1" : "p2") : "done";
    const issues = (l.issues || []).length ? `<ul class="issues">${l.issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : "";
    const when = l.last_called_at ? new Date(l.last_called_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "";
    const last = l.call_count ? `<div class="last">Last: ${esc((l.last_outcome || "").replace(/_/g, " "))} · ${l.call_count} call${l.call_count > 1 ? "s" : ""} · ${when}</div>` : "";
    const cb = l.stage === "callback" && l.callback_at ? `<div class="last"><b>Call back ${esc(new Date(l.callback_at).toLocaleString("en-IN", { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }))}</b></div>` : "";
    const outcomes = l.stage === "new" || l.stage === "callback" ? `
      <button data-o="no_answer">No answer</button>
      <button data-o="callback">Callback…</button>
      <button data-o="interested" class="good">Interested</button>
      <button data-o="won" class="good">Won</button>
      <button data-o="not_interested" class="bad">Not interested</button>
      <button data-o="has_website" class="bad">Has website</button>
      <button data-o="wrong_number" class="bad">Wrong number</button>
      <button data-o="do_not_call" class="bad">Don't call</button>` : l.stage === "interested" ? `
      <button data-o="won" class="good">Won</button>
      <button data-o="callback">Callback…</button>
      <button data-o="not_interested" class="bad">Not interested</button>` : `
      <button data-o="reopen">Move back to To call</button>`;
    const tierLabel = { A: "Best lead", B: "Good lead", C: "Lead" }[l.tier];
    const why = (l.reasons || []).filter((r) => !/^(No website|Their website|Website needs)/.test(r)).slice(0, 4);
    const whyHtml = why.length ? `<ul class="why">${why.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : "";
    return `
    <article class="lead" data-id="${l.id}">
      <h3>${esc(l.name)}${tierLabel ? ` <span class="tier t${l.tier}">${tierLabel}</span>` : ""}</h3>
      <div class="meta">${esc(CAT[l.category] || l.category)} · ${esc(areaOf(l))}</div>
      <span class="pill ${pillClass}">${esc(statusText(l))}</span>${issues}${whyHtml}
      <div class="phone">${esc(l.phone || "")}</div>${cb}${last}
      <div class="actions">
        <a class="btn call" href="tel:${esc(l.phone_intl || "")}">Call</a>
        <a class="btn wa" target="_blank" rel="noopener" href="https://wa.me/${digits}?text=${encodeURIComponent(whatsappText(l))}">WhatsApp</a>
        <a class="btn ghost" target="_blank" rel="noopener" href="${esc(maps)}">Map</a>
        ${site ? `<a class="btn ghost" target="_blank" rel="noopener" href="${esc(site)}">${esc(siteLabel)}</a>` : `<button class="btn ghost" disabled>${esc(siteLabel)}</button>`}
      </div>
      <details class="script"><summary>What to say</summary><p>${esc(script(l))}</p></details>
      <div class="outcomes">${outcomes}</div>
      <div class="note row"><textarea placeholder="Notes (owner's name, best time, price they asked…)">${esc(l.notes || "")}</textarea></div>
      <button class="btn ghost wide save-note">Save note</button>
    </article>`;
  }

  async function record(article, outcome, callbackAt) {
    const id = article.dataset.id;
    const note = article.querySelector("textarea").value;
    const buttons = article.querySelectorAll("button");
    buttons.forEach((b) => { b.disabled = true; });
    try {
      const res = await rpc("app_update_lead", { p_id: id, p_outcome: outcome, p_note: note || null, p_callback_at: callbackAt || null });
      const lead = leads.find((x) => x.id === id);
      const stays = (view === "to_call" && res.stage === "new") || view === res.stage || (view === "done" && ["not_interested", "wrong_number", "do_not_call", "skip"].includes(res.stage));
      const labels = { no_answer: "Saved: no answer - it moves to the end of the list", callback: "Callback saved", interested: "Marked interested 🎉", won: "Client won! 🎉",
        not_interested: "Marked not interested", has_website: "Removed - they have a website", wrong_number: "Marked wrong number", do_not_call: "Won't be called again", reopen: "Moved back to To call", note: "Note saved" };
      toast(labels[outcome] || "Saved");
      if (outcome === "note") {
        if (lead) lead.notes = note;
        buttons.forEach((b) => { b.disabled = false; });
      } else if (!stays || outcome === "no_answer") {
        leads = leads.filter((x) => x.id !== id);
        article.remove();
        if (!leads.length) loadLeads(true);
      } else {
        buttons.forEach((b) => { b.disabled = false; });
      }
      loadStats();
    } catch (e) {
      toast(e.message);
      buttons.forEach((b) => { b.disabled = false; });
    }
  }

  $("#lead-list").addEventListener("click", (e) => {
    const article = e.target.closest(".lead");
    if (!article) return;
    if (e.target.closest(".save-note")) return record(article, "note");
    const b = e.target.closest("button[data-o]");
    if (!b) return;
    if (b.dataset.o === "callback") return askCallback(article);
    record(article, b.dataset.o);
  });

  // ---------- callback picker ----------
  const pad = (n) => String(n).padStart(2, "0");
  const localValue = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  function at(daysAhead, hour) { const d = new Date(); d.setDate(d.getDate() + daysAhead); d.setHours(hour, 0, 0, 0); return d; }
  function askCallback(article) {
    const dlg = $("#callback-dialog");
    const input = $("#cb-when");
    input.value = localValue(at(1, 11));
    const inTwo = new Date(Date.now() + 2 * 3600e3);
    const monday = at(((8 - new Date().getDay()) % 7) || 7, 11);
    const quick = [["In 2 hours", inTwo], ["Tomorrow 11 AM", at(1, 11)], ["Tomorrow 5 PM", at(1, 17)], ["Monday 11 AM", monday]];
    $("#cb-quick").innerHTML = quick.map(([t, d], i) => `<button type="button" data-i="${i}">${t}</button>`).join("");
    $("#cb-quick").onclick = (ev) => { const q = ev.target.closest("button"); if (q) input.value = localValue(quick[q.dataset.i][1]); };
    dlg.onclose = () => {
      if (dlg.returnValue === "ok" && input.value) record(article, "callback", new Date(input.value).toISOString());
    };
    dlg.showModal();
  }

  // ---------- admin ----------
  async function loadAdmin() {
    const [s, jobs] = await Promise.all([loadStats(), rpc("app_jobs")]);
    $("#places").innerHTML = s.by_place.length ? `<table><tr><th>City</th><th class="num">No website</th><th class="num">Needs work</th><th class="num">Won</th><th class="num">Total</th></tr>` +
      s.by_place.map((p) => `<tr><td>${esc(p.city)}${p.country !== "IN" ? ", " + esc(p.country) : ""}</td><td class="num">${p.p1}</td><td class="num">${p.p2}</td><td class="num">${p.won}</td><td class="num">${p.total}</td></tr>`).join("") + `</table>` +
      `<p class="muted" style="margin-top:10px">Waiting for a website check: ${s.unchecked.toLocaleString("en-IN")} · Database ${s.db_mb} MB of 500 MB free</p>`
      : `<p class="muted">No cities yet.</p>`;
    $("#jobs").innerHTML = jobs.length ? jobs.map((j) => `<div class="job"><span class="status ${j.status}">${j.status}</span> · <b>${esc(j.city)}</b>, ${esc(COUNTRY[j.country]?.name || j.country)} · ${esc(j.category === "all" ? "all shop types" : CAT[j.category] || j.category)}
      <div class="muted" style="margin:4px 0 0">${esc(j.message || (j.status === "queued" ? "Starts with the next run" : ""))}</div></div>`).join("") : `<p class="muted">No searches yet.</p>`;
  }

  $("#queue-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await rpc("app_queue_job", { p_country: $("#q-country").value, p_city: $("#q-city").value.trim(), p_category: $("#q-category").value });
      $("#queue-msg").hidden = false;
      $("#queue-msg").textContent = `Added ${$("#q-city").value.trim()}. The agents pick it up on their next run.`;
      $("#q-city").value = "";
      loadAdmin();
    } catch (err) { toast(err.message); }
  });

  // ---------- team ----------
  async function loadTeam() {
    const members = await rpc("app_members");
    $("#members").innerHTML = members.map((m) => `
      <div class="member"><div><b>${esc(m.name)}</b> <span class="muted">· ${m.role} · ${m.calls} calls · ${m.won} won</span></div>
      ${m.id === me.id ? `<span class="muted">you</span>` : `<button class="btn ghost" data-m="${m.id}" data-a="${!m.active}">${m.active ? "Switch off" : "Switch on"}</button>`}</div>`).join("");
  }
  $("#members").addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-m]");
    if (!b) return;
    try { await rpc("app_set_member_active", { p_id: b.dataset.m, p_active: b.dataset.a === "true" }); loadTeam(); } catch (err) { toast(err.message); }
  });
  $("#member-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const name = $("#m-name").value.trim();
      const res = await rpc("app_add_member", { p_name: name, p_role: $("#m-role").value });
      const link = `${location.origin}${location.pathname}#code=${res.code}`;
      const msg = `Hi ${name}! Here's your Lead Finder link. Open it on your phone and add it to your home screen:\n${link}`;
      const box = $("#member-link");
      box.hidden = false;
      box.innerHTML = `<b>${esc(name)}'s login link</b> (shown only once - send it now):<br>${esc(link)}
        <div class="row"><button class="btn ghost" id="copy-link">Copy</button>
        <a class="btn wa" target="_blank" rel="noopener" href="https://wa.me/?text=${encodeURIComponent(msg)}">Send on WhatsApp</a></div>`;
      $("#copy-link").onclick = () => navigator.clipboard.writeText(link).then(() => toast("Copied"));
      $("#m-name").value = "";
      loadTeam();
    } catch (err) { toast(err.message); }
  });

  // ---------- settings ----------
  $("#settings-btn").addEventListener("click", () => {
    $("#s-name").value = store.get("lf_name", "");
    $("#s-company").value = store.get("lf_company", "");
    $("#s-price").value = store.get("lf_price", "");
    $("#settings").showModal();
  });
  $("#settings").addEventListener("close", () => {
    if ($("#settings").returnValue !== "save") return;
    store.set("lf_name", $("#s-name").value.trim());
    store.set("lf_company", $("#s-company").value.trim());
    store.set("lf_price", $("#s-price").value.trim());
    toast("Saved");
    if (view !== "admin" && view !== "team") loadLeads(true);
  });
  $("#logout-btn").addEventListener("click", () => logout(false));

  start();
})();
