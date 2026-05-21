/* ──────────────────────────────────────────────────────────────────────
   unfinished-world.js
   The fourth world: visitor impressions orbiting the constellation.

   UX philosophy:
   – Ask for country (echoes the exposition's international structure)
   – Free-form writing; soft prompts available but never mandatory
   – Comment bubbles orbit AROUND the image panel, not over it
   ────────────────────────────────────────────────────────────────────── */
"use strict";

const UW_API = "http://localhost:3800/api";

/* ── Soft prompt starters ───────────────────────────────────────────────
   These offer a first word, not a template.
   Clicking one pre-fills the textarea starter and moves cursor to end.
   The visitor is free to write anything — the chip is just a door.
   ─────────────────────────────────────────────────────────────────────── */
const PROMPTS = [
  { chip: "I see",            start: "I see "           },
  { chip: "I imagine",        start: "I imagine "       },
  { chip: "I wonder",         start: "I wonder "        },
  { chip: "It reminds me of", start: "It reminds me of " },
  { chip: "What strikes me",  start: "What strikes me " },
  { chip: "Across 160 years", start: "Across 160 years, " },
  { chip: "The catalogue missed", start: "What the catalogue never recorded was " },
];

/* ── Countries datalist (common, for autocomplete only) ────────────────── */
const COUNTRIES = [
  "Argentina","Australia","Austria","Belgium","Brazil","Canada","Chile","China",
  "Colombia","Czech Republic","Denmark","Egypt","Finland","France","Germany",
  "Greece","Hungary","India","Indonesia","Iran","Ireland","Israel","Italy",
  "Japan","Malaysia","Mexico","Morocco","Netherlands","New Zealand","Nigeria",
  "Norway","Pakistan","Peru","Philippines","Poland","Portugal","Romania",
  "Russia","Saudi Arabia","South Africa","South Korea","Spain","Sweden",
  "Switzerland","Taiwan","Thailand","Turkey","Ukraine","United Kingdom",
  "United States","Vietnam",
];

/* ── State ──────────────────────────────────────────────────────────── */
let currentExhibit = null;
let orbitBubbles   = [];   // { el, angle, rx, ry, speed, wobble, born }
let animFrame      = null;

/* ── DOM refs ───────────────────────────────────────────────────────── */
const bubbleLayer  = document.getElementById("bubble-layer");
const imagePanel   = document.getElementById("image-panel");
const commentPanel = document.getElementById("uw-comment-panel");
const essaySlot    = document.getElementById("image-panel-essay");

/* ── Populate datalist once ─────────────────────────────────────────── */
const dl = document.getElementById("country-datalist");
if (dl) COUNTRIES.forEach(c => {
  const opt = document.createElement("option");
  opt.value = c;
  dl.appendChild(opt);
});

/* ══════════════════════════════════════════════════════════════════════
   EVENTS FROM initial-local.js
   ══════════════════════════════════════════════════════════════════════ */

document.addEventListener("uwExhibitSelect", ev => {
  currentExhibit = ev.detail.exhibit;
  _clearOrbit();
  _buildPanel(currentExhibit);
  setTimeout(() => { if (currentExhibit) _fetchAndOrbit(currentExhibit); }, 520);
});

document.addEventListener("uwExhibitDeselect", () => {
  currentExhibit = null;
  _clearOrbit();
  _hidePanel();
});

/* ══════════════════════════════════════════════════════════════════════
   COMMENT PANEL
   ══════════════════════════════════════════════════════════════════════ */

function _buildPanel(exhibit) {
  if (!commentPanel) return;

  /* Exhibit title */
  const titleEl = document.getElementById("uwcp-title");
  if (titleEl) titleEl.textContent = exhibit.name || "";

  /* Voice count placeholder */
  const vtEl = document.getElementById("uwcp-voice-text");
  if (vtEl) vtEl.textContent = "—";

  /* Build prompt chips */
  const promptsEl = document.getElementById("uwcp-prompts");
  if (promptsEl) {
    promptsEl.innerHTML = PROMPTS.map(p =>
      `<button type="button" class="uwcp-chip" data-start="${escHtml(p.start)}">${escHtml(p.chip)}</button>`
    ).join("");

    promptsEl.querySelectorAll(".uwcp-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        const ta = document.getElementById("uwcp-body");
        if (!ta) return;
        const active = btn.classList.contains("active");
        promptsEl.querySelectorAll(".uwcp-chip").forEach(b => b.classList.remove("active"));
        if (active) {
          ta.value = "";
        } else {
          btn.classList.add("active");
          // If textarea is empty or still contains the old starter, replace it
          ta.value = btn.dataset.start;
          ta.setSelectionRange(ta.value.length, ta.value.length);
        }
        ta.focus();
        _validateSubmit();
      });
    });
  }

  /* Reset fields */
  const ta  = document.getElementById("uwcp-body");
  const sub = document.getElementById("uwcp-submit");
  const msg = document.getElementById("uwcp-msg");
  if (ta)  { ta.value = ""; ta.removeEventListener("input", _validateSubmit); ta.addEventListener("input", _validateSubmit); }
  if (sub) { const fresh = sub.cloneNode(true); sub.replaceWith(fresh); fresh.addEventListener("click", () => _submitComment(exhibit)); }
  if (msg) { msg.textContent = ""; msg.className = "uwcp-msg"; }
  _validateSubmit();

  /* Country & name reset */
  const ctry = document.getElementById("uwcp-country");
  const name = document.getElementById("uwcp-name");
  if (ctry) ctry.value = "";
  if (name) name.value = "";

  /* Show panel */
  commentPanel.setAttribute("aria-hidden", "false");
  commentPanel.classList.add("on");

  /* Image panel: suppress essay text */
  if (essaySlot) essaySlot.textContent = "";

  /* Fetch count */
  _fetchVoiceCount(String(exhibit.exhibitId || exhibit.id));
}

function _hidePanel() {
  if (!commentPanel) return;
  commentPanel.classList.remove("on");
  commentPanel.setAttribute("aria-hidden", "true");
  if (essaySlot) essaySlot.textContent = "";
}

function _validateSubmit() {
  const ta  = document.getElementById("uwcp-body");
  const btn = document.getElementById("uwcp-submit");
  if (ta && btn) btn.disabled = ta.value.trim().length < 2;
}

async function _fetchVoiceCount(exhibitId) {
  const el = document.getElementById("uwcp-voice-text");
  if (!el) return;
  try {
    const res = await fetch(`${UW_API}/comments?exhibitId=${encodeURIComponent(exhibitId)}&limit=200`);
    if (!res.ok) return;
    const rows = await res.json();
    const n = rows.length;
    const countries = new Set(rows.map(r => r.country).filter(Boolean));
    const c = countries.size;
    if (n === 0) {
      el.textContent = "no impressions yet";
    } else if (c >= 2) {
      el.textContent = `${n} voice${n > 1 ? "s" : ""} · ${c} countries`;
    } else {
      el.textContent = `${n} impression${n > 1 ? "s" : ""}`;
    }
  } catch (_) {
    el.textContent = "—";
  }
}

async function _submitComment(exhibit) {
  const ta   = document.getElementById("uwcp-body");
  const ctry = document.getElementById("uwcp-country");
  const name = document.getElementById("uwcp-name");
  const btn  = document.getElementById("uwcp-submit");
  const msg  = document.getElementById("uwcp-msg");
  if (!ta || !ta.value.trim()) return;
  if (btn) btn.disabled = true;

  const exhibitId = String(exhibit.exhibitId || exhibit.id);

  try {
    const res = await fetch(`${UW_API}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        exhibitId,
        username: name?.value.trim() || "Anonymous",
        country:  ctry?.value.trim() || "",
        world:    "visitor",
        content:  ta.value.trim(),
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const comment = await res.json();

    /* Confirmation message */
    if (msg) {
      msg.textContent = "Recorded. Your impression joins the constellation.";
      msg.className   = "uwcp-msg ok";
      setTimeout(() => { if (msg) { msg.textContent = ""; msg.className = "uwcp-msg"; } }, 5000);
    }

    /* Reset form */
    ta.value = "";
    if (ctry) ctry.value = "";
    if (name) name.value = "";
    document.querySelectorAll(".uwcp-chip").forEach(b => b.classList.remove("active"));
    _validateSubmit();

    /* Add new bubble to the orbit immediately */
    const label = _bubbleLabel(comment);
    _spawnBubble(label, exhibit.color || "#c4a882", true);

    /* Refresh voice count */
    _fetchVoiceCount(exhibitId);

  } catch (err) {
    console.error(err);
    if (msg) {
      msg.textContent = "Server unreachable — is the API running?";
      msg.className   = "uwcp-msg err";
    }
    if (btn) btn.disabled = false;
  }
}

/* ══════════════════════════════════════════════════════════════════════
   ORBITING COMMENT BUBBLES
   Orbit is an ellipse whose semi-axes are computed from the live
   image-panel bounding rect, guaranteeing bubbles stay outside.
   ══════════════════════════════════════════════════════════════════════ */

async function _fetchAndOrbit(exhibit) {
  const eid = String(exhibit.exhibitId || exhibit.id);
  let rows  = [];
  try {
    const res = await fetch(`${UW_API}/comments?exhibitId=${encodeURIComponent(eid)}&limit=10`);
    if (res.ok) rows = await res.json();
  } catch (_) {}

  const EMPTY = [
    "The first impression is yours.",
    "No words left here yet.",
    "This exhibit awaits a voice.",
  ];

  const items = rows.length ? rows : EMPTY.map(t => ({ content: t, username: "", country: "" }));
  const color = exhibit.color || "#c4a882";

  items.forEach((item, i) => {
    const label = typeof item === "string" ? item : _bubbleLabel(item);
    const angle = (i / items.length) * Math.PI * 2;
    _spawnBubble(label, color, false, angle);
  });

  _orbitTick();
}

/* Build a display label from a comment row */
function _bubbleLabel(row) {
  const text = (row.content || "").slice(0, 80) + ((row.content || "").length > 80 ? "…" : "");
  const who  = [row.username, row.country].filter(Boolean).join(" · ");
  return who ? `${text}\n— ${who}` : text;
}

function _spawnBubble(label, color, isNew = false, fixedAngle = null) {
  if (!bubbleLayer) return;
  const el = document.createElement("div");
  el.className  = isNew ? "visitor-bubble new" : "visitor-bubble";
  el.textContent = label;
  el.style.setProperty("--wc", color);
  bubbleLayer.appendChild(el);

  /* Each bubble gets its own orbit radii (base + small offset) so they
     don't all stack. The base is computed live in _orbitTick() from the
     panel rect; here we store just the extra per-bubble offset. */
  orbitBubbles.push({
    el,
    angle:       fixedAngle ?? (Math.random() * Math.PI * 2),
    radiusExtra: 10 + Math.random() * 50,   // px added on top of panel clearance
    speed:       (0.00014 + Math.random() * 0.00012) * (Math.random() < 0.5 ? 1 : -1),
    wobble:      Math.random() * Math.PI * 2,
    born:        performance.now(),
  });
}

const ORBIT_MARGIN = 55;  // minimum px of clear space outside the panel edge

function _orbitTick() {
  if (!imagePanel) return;

  /* If panel isn't visible yet, keep waiting */
  if (!imagePanel.classList.contains("on")) {
    animFrame = requestAnimationFrame(_orbitTick);
    return;
  }

  const r  = imagePanel.getBoundingClientRect();
  const cx = r.left + r.width  / 2;
  const cy = r.top  + r.height / 2;

  /* Base semi-axes: just enough to clear the panel */
  const baseRx = r.width  / 2 + ORBIT_MARGIN;
  const baseRy = r.height / 2 + ORBIT_MARGIN;

  const now = performance.now();

  orbitBubbles.forEach(b => {
    b.angle += b.speed;

    const age     = Math.min((now - b.born) / 900, 1);
    const wobbleY = Math.sin(now * 0.0008 + b.wobble) * 14;

    const rx = baseRx + b.radiusExtra;
    const ry = baseRy + b.radiusExtra * 0.6;

    const x = cx + Math.cos(b.angle) * rx;
    const y = cy + Math.sin(b.angle) * ry + wobbleY;

    b.el.style.left      = `${x}px`;
    b.el.style.top       = `${y}px`;
    b.el.style.opacity   = String(age * 0.88);
    b.el.style.transform = `translate(-50%, -50%) scale(${0.88 + age * 0.12})`;
  });

  animFrame = requestAnimationFrame(_orbitTick);
}

function _clearOrbit() {
  cancelAnimationFrame(animFrame);
  animFrame = null;
  orbitBubbles.forEach(b => b.el.remove());
  orbitBubbles = [];
}

/* ── Utility ────────────────────────────────────────────────────────── */
function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
