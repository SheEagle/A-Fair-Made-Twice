/* ──────────────────────────────────────────────────────────────────────
   unfinished-world.js  —  The Fourth World

   Thesis: The 1867 Exposition was a constructed exhibition with an
   inherent point of view. So is this digital one. Visitors are invited
   to observe, imagine, connect — and question.

   Bubble shapes/colours by prompt type:
     observe  → cool blue, pill
     imagine  → lavender, organic blob
     connect  → amber, rounded rectangle
     question → rose-pink, angular / dashed
     free     → parchment, default pill

   New meaningful fields:
     country     — echoes the Exposition's national structure
     perspective — who is looking (student / researcher / artist / …)
     prompt_type — which mode was used (stored in DB, drives visual)
   ────────────────────────────────────────────────────────────────────── */
"use strict";

const UW_API = "http://localhost:3800/api";

/* ── Prompt categories ─────────────────────────────────────────────────
   Each category drives bubble appearance. Chips pre-fill a natural starter.
   ─────────────────────────────────────────────────────────────────────── */
const PROMPT_CATS = [
  {
    type:  "observe",
    label: "Observe",
    chips: [
      { chip: "What I notice",    start: "What I notice: "          },
      { chip: "On second look,",  start: "On second look, "         },
    ],
  },
  {
    type:  "imagine",
    label: "Imagine",
    chips: [
      { chip: "I picture",        start: "I picture "               },
      { chip: "In 1867,",         start: "In 1867, "                },
      { chip: "Behind this:",     start: "Behind this object: "     },
    ],
  },
  {
    type:  "connect",
    label: "Connect",
    chips: [
      { chip: "Still today:",     start: "Still relevant today: "   },
      { chip: "A century later,", start: "A century later, "        },
    ],
  },
  {
    type:  "question",
    label: "Question",
    chips: [
      { chip: "Missing:",         start: "Missing from this: "      },
      { chip: "Unrecorded:",      start: "Left unrecorded here: "   },
      { chip: "What this cost:",  start: "What this cost someone: " },
    ],
  },
];

/* Default textarea placeholder when no chip is active ─────────────────── */
const PLACEHOLDERS = {
  free:     "What does this exhibition choose not to show? Name it.",
  observe:  "What else do you see here — beyond what the catalogue names?",
  imagine:  "Whose hands or lives does this object carry — unrecorded?",
  connect:  "What does this still mean today, 160 years on?",
  question: "What is absent from this room — and why?",
};

/* ── Common countries for quick-select ────────────────────────────────
   Ordered to reflect the 1867 Exposition's prominent participating nations
   plus contemporary reach.
   ─────────────────────────────────────────────────────────────────────── */
const COUNTRY_CHIPS = [
  "France","United Kingdom","Germany","United States",
  "Italy","Japan","China","Russia","India","Egypt",
  "Brazil","Australia",
];

/* Extended list for datalist autocomplete */
const ALL_COUNTRIES = [
  ...COUNTRY_CHIPS,
  "Afghanistan","Algeria","Argentina","Austria","Belgium","Canada","Chile",
  "Colombia","Czech Republic","Denmark","Finland","Greece","Hungary","Indonesia",
  "Iran","Ireland","Israel","Malaysia","Mexico","Morocco","Netherlands",
  "New Zealand","Nigeria","Norway","Pakistan","Peru","Philippines","Poland",
  "Portugal","Romania","Saudi Arabia","South Africa","South Korea","Spain",
  "Sweden","Switzerland","Taiwan","Thailand","Turkey","Ukraine","Vietnam",
];

/* ── Perspective options ────────────────────────────────────────────── */
const PERSPECTIVES = [
  { label: "General visitor",   value: "general"       },
  { label: "Student",           value: "student"       },
  { label: "Researcher",        value: "researcher"    },
  { label: "Artist",            value: "artist"        },
  { label: "Museum professional", value: "professional" },
  { label: "Local",             value: "local"         },
];

/* ── Empty-state placeholders (no real comments yet) ─────────────────
   Shown only when the exhibit has no visitor impressions.
   Removed the moment the first real comment is submitted.
   ─────────────────────────────────────────────────────────────────── */
const EMPTY_PLACEHOLDERS = [
  "No impressions recorded yet.",
  "Be the first to leave your voice here.",
];

/* ── State ──────────────────────────────────────────────────────────── */
let currentExhibit  = null;
let orbitBubbles    = [];   // { el, angle, rx, ry, speed, wobble, born, isPlaceholder }
let animFrame       = null;
let activeType      = "free";
let activeCountry   = "";
let activePerspective = "";
let hasRealComments = false;

/* ── DOM refs ───────────────────────────────────────────────────────── */
const bubbleLayer   = document.getElementById("bubble-layer");
const imagePanel    = document.getElementById("image-panel");
const commentPanel  = document.getElementById("uw-comment-panel");
const modalBackdrop = document.getElementById("uw-modal-backdrop");
const inviteBar     = document.getElementById("uw-mark-invite");
const essaySlot     = document.getElementById("image-panel-essay");

/* ── Invite bar: show when exhibit selected, opens modal on click ────── */
function _showInvite() {
  if (!inviteBar) return;
  inviteBar.removeAttribute("aria-hidden");
  /* Double rAF ensures the browser commits the opacity:0 initial state
     before adding .on, so the CSS transition fires correctly */
  requestAnimationFrame(() => requestAnimationFrame(() => inviteBar.classList.add("on")));
}
function _hideInvite() {
  if (!inviteBar) return;
  inviteBar.classList.remove("on");
  inviteBar.setAttribute("aria-hidden", "true");
}

document.getElementById("uwmi-btn")?.addEventListener("click", () => {
  if (currentExhibit) {
    _hideInvite();
    _buildPanel(currentExhibit);
  }
});

/* ── Modal close: dismiss modal, restore invite bar ─────────────────── */
function _closeModal() {
  _hidePanel();
  if (currentExhibit) _showInvite();
}

document.getElementById("uw-modal-close")?.addEventListener("click", _closeModal);
modalBackdrop?.addEventListener("click", _closeModal);
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && commentPanel?.classList.contains("on")) _closeModal();
});

/* ── Build country datalist ────────────────────────────────────────── */
const dl = document.getElementById("uwcp-country-dl");
if (dl) ALL_COUNTRIES.forEach(c => {
  const o = document.createElement("option"); o.value = c; dl.appendChild(o);
});

/* ══════════════════════════════════════════════════════════════════════
   EVENTS
   ══════════════════════════════════════════════════════════════════════ */

document.addEventListener("uwExhibitSelect", ev => {
  currentExhibit = ev.detail.exhibit;
  _clearOrbit();
  _hidePanel();      // close any open modal from a previous exhibit
  _showInvite();     // show the floating invite bar
  const captured = currentExhibit;
  setTimeout(() => { if (currentExhibit === captured) _fetchAndOrbit(captured); }, 520);
});

document.addEventListener("uwExhibitDeselect", () => {
  currentExhibit = null;
  activeType = "free";
  _clearOrbit();
  _hideInvite();
  _hidePanel();
});

// Hide invite bar and modal when leaving Unfinished World
new MutationObserver(() => {
  if (document.body.dataset.world !== "unfinished") {
    _hideInvite();
    _hidePanel();
  }
}).observe(document.body, { attributes: true, attributeFilter: ["data-world"] });

/* ══════════════════════════════════════════════════════════════════════
   PANEL
   ══════════════════════════════════════════════════════════════════════ */

function _buildPanel(exhibit) {
  if (!commentPanel) return;

  activeType        = "free";
  activeCountry     = "";
  activePerspective = "";
  hasRealComments   = false;

  /* Title */
  const t = document.getElementById("uwcp-title");
  if (t) t.textContent = exhibit.name || "";

  /* Voice count */
  const vt = document.getElementById("uwcp-voice-text");
  if (vt) vt.textContent = "—";

  /* ── Prompt chips: category label + selectable starters ─────────── */
  const promptsEl = document.getElementById("uwcp-prompts");
  if (promptsEl) {
    promptsEl.innerHTML = PROMPT_CATS.map(cat => `
      <div class="uwcp-cat">
        <span class="uwcp-cat-label uwcp-cat-${cat.type}">${escHtml(cat.label)}</span>
        ${cat.chips.map(ch => `
          <button type="button"
                  class="uwcp-chip uwcp-chip-${cat.type}"
                  data-type="${cat.type}"
                  data-start="${escHtml(ch.start)}">${escHtml(ch.chip)}</button>
        `).join("")}
      </div>`).join("");

    promptsEl.querySelectorAll(".uwcp-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        const ta = document.getElementById("uwcp-body");
        if (!ta) return;
        const wasActive = btn.classList.contains("active");
        promptsEl.querySelectorAll(".uwcp-chip").forEach(b => b.classList.remove("active"));
        if (wasActive) {
          activeType = "free";
          ta.value = "";
          ta.placeholder = PLACEHOLDERS.free;
        } else {
          btn.classList.add("active");
          activeType = btn.dataset.type;
          ta.placeholder = PLACEHOLDERS[activeType] || PLACEHOLDERS.free;
          ta.value = btn.dataset.start;
          ta.setSelectionRange(ta.value.length, ta.value.length);
        }
        ta.focus();
        _validateSubmit();
      });
    });
  }

  /* ── Country chips ──────────────────────────────────────────────── */
  const ccEl = document.getElementById("uwcp-country-chips");
  if (ccEl) {
    ccEl.innerHTML = COUNTRY_CHIPS.map(c =>
      `<button type="button" class="uwcp-country-chip" data-val="${escHtml(c)}">${escHtml(c)}</button>`
    ).join("");
    ccEl.querySelectorAll(".uwcp-country-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        const wasActive = btn.classList.contains("active");
        ccEl.querySelectorAll(".uwcp-country-chip").forEach(b => b.classList.remove("active"));
        const ci = document.getElementById("uwcp-country");
        if (wasActive) {
          activeCountry = "";
          if (ci) ci.value = "";
        } else {
          btn.classList.add("active");
          activeCountry = btn.dataset.val;
          if (ci) { ci.value = ""; ci.placeholder = btn.dataset.val; }
        }
      });
    });
    /* Typing in country field clears chip selection */
    const ci = document.getElementById("uwcp-country");
    if (ci) {
      ci.addEventListener("input", () => {
        activeCountry = ci.value.trim();
        ccEl.querySelectorAll(".uwcp-country-chip").forEach(b => b.classList.remove("active"));
      });
    }
  }

  /* ── Perspective chips ──────────────────────────────────────────── */
  const pcEl = document.getElementById("uwcp-perspective-chips");
  if (pcEl) {
    pcEl.innerHTML = PERSPECTIVES.map(p =>
      `<button type="button" class="uwcp-persp-chip" data-val="${escHtml(p.value)}">${escHtml(p.label)}</button>`
    ).join("");
    pcEl.querySelectorAll(".uwcp-persp-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        const wasActive = btn.classList.contains("active");
        pcEl.querySelectorAll(".uwcp-persp-chip").forEach(b => b.classList.remove("active"));
        activePerspective = wasActive ? "" : btn.dataset.val;
        if (!wasActive) btn.classList.add("active");
      });
    });
  }

  /* ── Reset compose ──────────────────────────────────────────────── */
  const ta  = document.getElementById("uwcp-body");
  const sub = document.getElementById("uwcp-submit");
  const msg = document.getElementById("uwcp-msg");
  const ci  = document.getElementById("uwcp-country");
  const po  = document.getElementById("uwcp-perspective-other");
  if (ta)  { ta.value = ""; ta.placeholder = PLACEHOLDERS.free; ta.removeEventListener("input", _validateSubmit); ta.addEventListener("input", _validateSubmit); }
  if (sub) { const f = sub.cloneNode(true); sub.replaceWith(f); f.addEventListener("click", () => _submit(exhibit)); }
  if (msg) { msg.textContent = ""; msg.className = "uwcp-msg"; }
  if (ci)  { ci.value = ""; ci.placeholder = "Other country…"; }
  if (po)  {
    po.value = "";
    po.removeEventListener("input", _onPerspOther);
    po.addEventListener("input", _onPerspOther);
  }
  _validateSubmit();

  /* Show modal */
  commentPanel.setAttribute("aria-hidden", "false");
  commentPanel.classList.add("on");
  modalBackdrop?.setAttribute("aria-hidden", "false");
  modalBackdrop?.classList.add("on");
  if (essaySlot) essaySlot.textContent = "";
  /* Trap focus to first interactive element */
  setTimeout(() => commentPanel.querySelector("textarea,button,input")?.focus(), 80);

  _fetchVoiceCount(String(exhibit.exhibitId || exhibit.id));
}

function _hidePanel() {
  if (!commentPanel) return;
  commentPanel.classList.remove("on");
  commentPanel.setAttribute("aria-hidden", "true");
  modalBackdrop?.classList.remove("on");
  modalBackdrop?.setAttribute("aria-hidden", "true");
  if (essaySlot) essaySlot.textContent = "";
}

function _validateSubmit() {
  const ta  = document.getElementById("uwcp-body");
  const btn = document.getElementById("uwcp-submit");
  if (ta && btn) btn.disabled = ta.value.trim().length < 2;
}

function _onPerspOther() {
  const po = document.getElementById("uwcp-perspective-other");
  if (!po) return;
  const val = po.value.trim();
  if (val) {
    /* Clear chip selection when free text is entered */
    document.querySelectorAll(".uwcp-persp-chip").forEach(b => b.classList.remove("active"));
    activePerspective = val;
  } else {
    activePerspective = "";
  }
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
    if (n === 0)        el.textContent = "no impressions yet";
    else if (c >= 2)    el.textContent = `${n} voice${n>1?"s":""} · ${c} countries`;
    else                el.textContent = `${n} impression${n>1?"s":""}`;
  } catch (_) { el.textContent = "—"; }
}

async function _submit(exhibit) {
  const ta   = document.getElementById("uwcp-body");
  const ci   = document.getElementById("uwcp-country");
  const po   = document.getElementById("uwcp-perspective-other");
  const btn  = document.getElementById("uwcp-submit");
  const msg  = document.getElementById("uwcp-msg");
  if (!ta || !ta.value.trim()) return;
  if (btn) btn.disabled = true;

  const country     = activeCountry || ci?.value.trim() || "";
  const perspective = activePerspective || po?.value.trim() || "";

  try {
    const res = await fetch(`${UW_API}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        exhibitId:   String(exhibit.exhibitId || exhibit.id),
        username:    "Anonymous",
        country,
        perspective,
        prompt_type: activeType,
        world:       "visitor",
        content:     ta.value.trim(),
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const comment = await res.json();

    /* First real comment — remove placeholder bubbles */
    if (!hasRealComments) {
      hasRealComments = true;
      orbitBubbles = orbitBubbles.filter(b => {
        if (b.isPlaceholder) { b.el.remove(); return false; }
        return true;
      });
    }

    if (msg) {
      msg.textContent = "Recorded. Your impression joins the constellation.";
      msg.className   = "uwcp-msg ok";
    }

    /* Reset */
    ta.value = "";
    ta.placeholder = PLACEHOLDERS.free;
    if (ci) { ci.value = ""; ci.placeholder = "Other country…"; }
    const poEl = document.getElementById("uwcp-perspective-other");
    if (poEl) poEl.value = "";
    activeType = "free"; activeCountry = ""; activePerspective = "";
    document.querySelectorAll(".uwcp-chip,.uwcp-country-chip,.uwcp-persp-chip")
      .forEach(b => b.classList.remove("active"));
    _validateSubmit();

    /* Auto-close modal immediately after confirmation */
    setTimeout(() => _closeModal(), 800);

    /* New bubble orbits immediately */
    _spawnBubble(comment, exhibit.color || "#c4a882", false, true);
    _fetchVoiceCount(String(exhibit.exhibitId || exhibit.id));

  } catch (err) {
    console.error(err);
    if (msg) { msg.textContent = "Server unreachable."; msg.className = "uwcp-msg err"; }
    if (btn) btn.disabled = false;
  }
}

/* ══════════════════════════════════════════════════════════════════════
   ORBITING BUBBLES
   Elliptical orbit with semi-axes derived from the live panel rect.
   Each bubble carries its prompt_type for visual differentiation.
   ══════════════════════════════════════════════════════════════════════ */

const ORBIT_MARGIN = 24;   // clear gap between panel edge and nearest bubble edge

async function _fetchAndOrbit(exhibit) {
  const eid = String(exhibit.exhibitId || exhibit.id);
  let rows  = [];
  try {
    const res = await fetch(`${UW_API}/comments?exhibitId=${encodeURIComponent(eid)}&limit=12`);
    if (res.ok) rows = await res.json();
  } catch (_) {}

  if (rows.length > 0) {
    hasRealComments = true;
    rows.forEach((row, i) => {
      const angle = (i / rows.length) * Math.PI * 2;
      _spawnBubble(row, exhibit.color || "#c4a882", false, false, angle);
    });
  } else {
    /* Empty state: gentle placeholder ghosts */
    EMPTY_PLACEHOLDERS.forEach((text, i) => {
      const angle = (i / EMPTY_PLACEHOLDERS.length) * Math.PI * 2 + Math.PI * 0.25;
      _spawnPlaceholder(text, angle);
    });
  }
  _orbitTick();
}

const TYPE_LABELS = {
  observe: "Observe", imagine: "Imagine", connect: "Connect",
  question: "Question", free: "",
};

function _spawnBubble(row, _accent, _isNew, isJustPosted = false, fixedAngle = null) {
  if (!bubbleLayer) return;
  const el = document.createElement("div");
  const type = row.prompt_type || "free";
  el.className = `visitor-bubble vb-${type}${isJustPosted ? " vb-new" : ""}`;

  /* Structured HTML: type-tag / content / attribution */
  const text = (row.content || "").slice(0, 100) + ((row.content||"").length > 100 ? "…" : "");
  const attrParts = [
    row.username && row.username !== "Anonymous" ? row.username : null,
    row.country  || null,
    row.perspective ? _perspLabel(row.perspective) : null,
  ].filter(Boolean);
  const typeLabel = TYPE_LABELS[type] || "";

  el.innerHTML =
    (typeLabel ? `<span class="vb-type-tag">${typeLabel}</span>` : "") +
    `<span class="vb-content">${escHtml(text)}</span>` +
    (attrParts.length ? `<span class="vb-attr">— ${escHtml(attrParts.join(" · "))}</span>` : "");

  bubbleLayer.appendChild(el);

  /* stagger ring: index within current orbit determines which of 3 concentric
     rings this bubble lives on, so adjacent bubbles at similar angles don't sit
     on top of each other */
  const ring = orbitBubbles.length % 3;   // 0 / 1 / 2
  orbitBubbles.push({
    el,
    angle:         fixedAngle ?? (Math.random() * Math.PI * 2),
    ring,                                  // used by _orbitTick for radius stagger
    speed:         (0.00008 + Math.random() * 0.00010) * (Math.random() < 0.5 ? 1 : -1),
    wobble:        Math.random() * Math.PI * 2,
    born:          performance.now(),
    isPlaceholder: false,
  });
}

function _spawnPlaceholder(text, fixedAngle) {
  if (!bubbleLayer) return;
  const el = document.createElement("div");
  el.className = "visitor-bubble vb-placeholder";
  el.innerHTML = `<span class="vb-content">${escHtml(text)}</span>`;
  bubbleLayer.appendChild(el);
  orbitBubbles.push({
    el,
    angle:         fixedAngle,
    ring:          orbitBubbles.length % 3,
    speed:         0.00006 * (Math.random() < 0.5 ? 1 : -1),
    wobble:        Math.random() * Math.PI * 2,
    born:          performance.now(),
    isPlaceholder: true,
  });
}

function _orbitTick() {
  if (!imagePanel) return;
  if (!imagePanel.classList.contains("on")) {
    animFrame = requestAnimationFrame(_orbitTick);
    return;
  }

  const r   = imagePanel.getBoundingClientRect();
  const cx  = r.left + r.width  / 2;
  const cy  = r.top  + r.height / 2;
  const now = performance.now();

  /* ── Soft angular repulsion — keeps bubbles spread apart ──────────────
     For each pair, if their angles are too close, gently push them apart.
     This runs every frame so the separation is maintained as they orbit.  */
  const N = orbitBubbles.length;
  if (N > 1) {
    const idealGap = (Math.PI * 2) / N;
    const minGap   = Math.max(0.42, idealGap * 0.55);   // ~24° minimum

    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        let diff = orbitBubbles[i].angle - orbitBubbles[j].angle;
        // wrap to (−π, π]
        diff = ((diff % (Math.PI * 2)) + Math.PI * 3) % (Math.PI * 2) - Math.PI;
        if (Math.abs(diff) < minGap) {
          const push = (minGap - Math.abs(diff)) * 0.003 * Math.sign(diff || 1);
          orbitBubbles[i].angle += push;
          orbitBubbles[j].angle -= push;
        }
      }
    }
  }

  orbitBubbles.forEach(b => {
    b.angle += b.speed;
    const age     = Math.min((now - b.born) / 900, 1);
    const wobbleY = Math.sin(now * 0.0006 + b.wobble) * 7;

    /* Radius: panel half-size + gap + actual bubble DOM half-size + ring offset.
       Using offsetWidth/Height means the bubble edge always clears the panel edge
       regardless of content length or font size. */
    const bHalfW = b.el.offsetWidth  > 0 ? b.el.offsetWidth  / 2 + 16 : 130;
    const bHalfH = b.el.offsetHeight > 0 ? b.el.offsetHeight / 2 + 12 : 46;
    const ringOffset = b.ring * 28;         // 0 / 28 / 56 px — concentric layers

    const rx = r.width  / 2 + ORBIT_MARGIN + bHalfW + ringOffset;
    const ry = r.height / 2 + ORBIT_MARGIN + bHalfH + ringOffset * 0.6;

    b.el.style.left      = `${cx + Math.cos(b.angle) * rx}px`;
    b.el.style.top       = `${cy + Math.sin(b.angle) * ry + wobbleY}px`;
    b.el.style.opacity   = String(age * (b.isPlaceholder ? 0.55 : 1.0));
    b.el.style.transform = `translate(-50%,-50%) scale(${0.88 + age * 0.12})`;
  });

  animFrame = requestAnimationFrame(_orbitTick);
}

function _clearOrbit() {
  cancelAnimationFrame(animFrame);
  animFrame = null;
  orbitBubbles.forEach(b => b.el.remove());
  orbitBubbles = [];
}

function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function _perspLabel(val) {
  const p = PERSPECTIVES.find(x => x.value === val);
  return p ? p.label : val;
}
