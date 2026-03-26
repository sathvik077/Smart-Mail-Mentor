"use strict";

const API = "http://localhost:8000";

// ── Screen management ──────────────────────────────────────────────────────

const screens = {
  loading:   document.getElementById("screen-loading"),
  auth:      document.getElementById("screen-auth"),
  form:      document.getElementById("screen-form"),
  fetching:  document.getElementById("screen-fetching"),
  results:   document.getElementById("screen-results"),
  error:     document.getElementById("screen-error"),
};

function show(name) {
  Object.values(screens).forEach(s => s.classList.add("hidden"));
  screens[name].classList.remove("hidden");
}

// ── Boot ───────────────────────────────────────────────────────────────────

(async function init() {
  show("loading");
  try {
    const resp = await fetch(`${API}/auth/status`, { signal: AbortSignal.timeout(4000) });
    const data = await resp.json();
    if (data.authenticated) {
      show("form");
    } else {
      show("auth");
    }
  } catch {
    setError(
      "Cannot reach the backend on localhost:8000.\n" +
      "Make sure the server is running: uvicorn main:app --host 127.0.0.1 --port 8000"
    );
  }
})();

// ── Auth ───────────────────────────────────────────────────────────────────

document.getElementById("btn-connect").addEventListener("click", async () => {
  try {
    const resp = await fetch(`${API}/auth/gmail`);
    const data = await resp.json();
    chrome.tabs.create({ url: data.auth_url });
    // Poll for auth completion
    pollAuth();
  } catch (err) {
    setError("Failed to start Gmail auth: " + err.message);
  }
});

function pollAuth() {
  let attempts = 0;
  const interval = setInterval(async () => {
    attempts++;
    try {
      const resp = await fetch(`${API}/auth/status`);
      const data = await resp.json();
      if (data.authenticated) {
        clearInterval(interval);
        show("form");
      }
    } catch { /* keep polling */ }
    if (attempts > 60) clearInterval(interval); // give up after ~60s
  }, 1000);
}

// ── Mode toggle ────────────────────────────────────────────────────────────

const countFields     = document.getElementById("count-fields");
const daterangeFields = document.getElementById("daterange-fields");
let currentMode = "count";

document.querySelectorAll(".toggle-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".toggle-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentMode = btn.dataset.mode;
    countFields.classList.toggle("hidden", currentMode !== "count");
    daterangeFields.classList.toggle("hidden", currentMode !== "daterange");
    // default dates to last 7 days
    if (currentMode === "daterange" && !document.getElementById("end-date").value) {
      const today = new Date();
      const week  = new Date(today); week.setDate(week.getDate() - 7);
      document.getElementById("end-date").value   = fmtDate(today);
      document.getElementById("start-date").value = fmtDate(week);
    }
  });
});

function fmtDate(d) {
  return d.toISOString().slice(0, 10);
}

// ── Summarize ──────────────────────────────────────────────────────────────

document.getElementById("btn-summarize").addEventListener("click", runSummarize);

async function runSummarize() {
  const topPerCat = parseInt(document.getElementById("top-per-cat").value, 10);

  let payload;
  if (currentMode === "count") {
    payload = {
      mode: "count",
      count: parseInt(document.getElementById("email-count").value, 10),
      top_per_category: topPerCat,
    };
  } else {
    const start = document.getElementById("start-date").value;
    const end   = document.getElementById("end-date").value;
    if (!start || !end) {
      alert("Please select both a start and end date.");
      return;
    }
    if (start > end) {
      alert("Start date must be before end date.");
      return;
    }
    payload = { mode: "daterange", start_date: start, end_date: end, top_per_category: topPerCat };
  }

  show("fetching");
  document.getElementById("fetch-status").textContent = "Fetching emails…";

  try {
    const resp = await fetch(`${API}/api/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(120_000),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || resp.statusText);
    }

    const data = await resp.json();
    renderResults(data);
  } catch (err) {
    setError(err.message);
  }
}

// ── Results rendering ──────────────────────────────────────────────────────

const CAT_LABELS = {
  business:   { label: "Business",   icon: "💼" },
  promotions: { label: "Promotions", icon: "🏷️" },
  social:     { label: "Social",     icon: "👥" },
  updates:    { label: "Updates",    icon: "📬" },
  personal:   { label: "Personal",   icon: "👤" },
  forums:     { label: "Forums",     icon: "💬" },
};

function renderResults(data) {
  const meta    = data.metadata || {};
  const summary = data.summary  || {};

  document.getElementById("meta-count").textContent =
    `${meta.total_fetched ?? 0} emails`;
  document.getElementById("meta-time").textContent =
    `${meta.processing_time_ms ?? 0} ms`;

  const container = document.getElementById("results-container");
  container.innerHTML = "";

  const catOrder = ["business", "promotions", "social", "updates", "personal", "forums"];
  const cats = catOrder.filter(c => summary[c] && summary[c].emails.length > 0);

  if (cats.length === 0) {
    container.innerHTML = `<p class="muted" style="padding:16px 0;text-align:center">
      No emails found for the selected criteria.</p>`;
    show("results");
    return;
  }

  cats.forEach(cat => {
    const info  = summary[cat];
    const meta  = CAT_LABELS[cat] || { label: cat, icon: "📧" };
    const section = buildCategorySection(cat, meta, info);
    container.appendChild(section);
  });

  show("results");
}

function buildCategorySection(cat, meta, info) {
  const section = document.createElement("div");
  section.className = `category-section cat-${cat}`;

  const header = document.createElement("div");
  header.className = "category-header";
  header.innerHTML = `
    <span>${meta.icon} ${meta.label}</span>
    <span class="cat-count">${info.total_in_category} emails · top ${info.showing}</span>
    <svg class="chevron" width="12" height="12" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" stroke-width="2.5">
      <polyline points="6 9 12 15 18 9"/>
    </svg>`;

  const body = document.createElement("div");
  body.className = "category-body";

  info.emails.forEach(email => {
    body.appendChild(buildEmailCard(email, cat));
  });

  // Collapse/expand on header click
  header.addEventListener("click", () => {
    header.classList.toggle("collapsed");
    body.classList.toggle("collapsed");
  });

  section.appendChild(header);
  section.appendChild(body);
  return section;
}

function buildEmailCard(email, category) {
  const card = document.createElement("div");
  card.className = "email-card";

  const score    = email.priority_score ?? 0;
  const badgeCls = score >= 0.6 ? "badge-high" : score >= 0.35 ? "badge-medium" : "badge-low";
  const badgeTxt = score >= 0.6 ? "High"       : score >= 0.35 ? "Med"          : "Low";

  const senderDisplay = email.sender_name || email.sender;
  const dateStr       = email.received_at
    ? new Date(email.received_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : "";

  card.innerHTML = `
    <div class="email-card-header">
      <span class="email-rank">#${email.rank}</span>
      <span class="email-sender" title="${email.sender}">${esc(senderDisplay)}</span>
      <span class="priority-badge ${badgeCls}">${badgeTxt}</span>
      <span style="font-size:10px;color:#9aa0a6;white-space:nowrap;margin-left:4px">${dateStr}</span>
    </div>
    <div class="email-subject">${esc(email.subject)}</div>
    <div class="email-summary">${esc(email.summary || "")}</div>
    ${buildInsights(email, category)}
  `;

  // Expand/collapse summary on click
  card.addEventListener("click", () => card.classList.toggle("expanded"));

  return card;
}

function buildInsights(email, category) {
  const chips = [];

  if (category === "promotions") {
    const p = email.promo_details || {};
    if (p.coupon_code)   chips.push(`<span class="insight-chip chip-coupon">🎫 ${esc(p.coupon_code)}</span>`);
    if (p.discount)      chips.push(`<span class="insight-chip chip-discount">💰 ${esc(p.discount)}</span>`);
    if (p.expiry_date)   chips.push(`<span class="insight-chip chip-expiry">⏰ Exp: ${esc(p.expiry_date)}</span>`);
    if (p.free_shipping) chips.push(`<span class="insight-chip chip-shipping">🚚 Free shipping</span>`);
  }

  if (category === "business") {
    const actions   = email.action_items  || [];
    const deadlines = email.deadlines     || [];
    actions.slice(0, 2).forEach(a =>
      chips.push(`<span class="insight-chip chip-action">✓ ${esc(truncate(a, 40))}</span>`)
    );
    deadlines.slice(0, 1).forEach(d =>
      chips.push(`<span class="insight-chip chip-deadline">📅 ${esc(truncate(d, 40))}</span>`)
    );
  }

  if (chips.length === 0) return "";
  return `<div class="insights-row">${chips.join("")}</div>`;
}

// ── New search ─────────────────────────────────────────────────────────────

document.getElementById("btn-new-search").addEventListener("click", () => show("form"));
document.getElementById("btn-retry").addEventListener("click", () => show("form"));

// ── Settings ───────────────────────────────────────────────────────────────

const settingsPanel = document.getElementById("settings-panel");

document.getElementById("btn-settings").addEventListener("click", async () => {
  settingsPanel.classList.remove("hidden");
  try {
    const resp = await fetch(`${API}/api/preferences`);
    const prefs = await resp.json();
    document.getElementById("pref-keywords").value = (prefs.priority_keywords || []).join(", ");
    document.getElementById("pref-senders").value  = (prefs.important_senders || []).join(", ");
    document.getElementById("pref-domains").value  = (prefs.important_domains || []).join(", ");
  } catch { /* show empty */ }
});

document.getElementById("btn-close-settings").addEventListener("click", () => {
  settingsPanel.classList.add("hidden");
});

document.getElementById("btn-save-prefs").addEventListener("click", async () => {
  const split = s => s.split(",").map(x => x.trim()).filter(Boolean);
  const payload = {
    priority_keywords: split(document.getElementById("pref-keywords").value),
    important_senders: split(document.getElementById("pref-senders").value),
    important_domains: split(document.getElementById("pref-domains").value),
  };
  try {
    await fetch(`${API}/api/preferences`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const msg = document.getElementById("prefs-saved-msg");
    msg.classList.remove("hidden");
    setTimeout(() => msg.classList.add("hidden"), 2000);
  } catch (err) {
    alert("Failed to save: " + err.message);
  }
});

// ── Helpers ────────────────────────────────────────────────────────────────

function setError(msg) {
  document.getElementById("error-message").textContent = msg;
  show("error");
}

function esc(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function truncate(str, max) {
  return str.length > max ? str.slice(0, max) + "…" : str;
}
