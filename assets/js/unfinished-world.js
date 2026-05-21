/* ──────────────────────────────────────────────────────────────────────
   unfinished-world.js
   Fourth world in the Paris 1867 constellation.
   – Orbiting visitor-comment pills around the image panel
   – Dedicated right-side comment form with HCI quick-tag starters
   Communicates with initial-local.js via CustomEvents:
     "uwExhibitSelect"   { detail: { exhibit, index } }
     "uwExhibitDeselect"
   ────────────────────────────────────────────────────────────────────── */
"use strict";

const UW_API = "http://localhost:3800/api";

/* ── Quick-response tags (HCI: recognition over recall) ────────────────
   label   shown on button
   starter sentence fragment pre-filled into textarea
   icon    tiny unicode glyph (decorative only)
   ─────────────────────────────────────────────────────────────────────── */
const TAGS = [
  { label: "Wonder",     icon: "✦", starter: "What struck me with wonder was " },
  { label: "Unease",     icon: "◈", starter: "There was something unsettling here — " },
  { label: "Familiar",   icon: "◎", starter: "This reminded me of " },
  { label: "Overlooked", icon: "△", starter: "Most visitors seemed to miss " },
  { label: "Haunting",   icon: "◇", starter: "I couldn't quite forget " },
  { label: "Ordinary",   icon: "○", starter: "What surprised me was how ordinary " },
  { label: "Grand",      icon: "◉", starter: "The scale of it felt " },
  { label: "Personal",   icon: "◑", starter: "Standing here, I thought of " },
];

/* ── State ──────────────────────────────────────────────────────────── */
let currentExhibit  = null;
let orbitBubbles    = [];       // { el, angle, radius, speed, wobble, born }
let animFrame       = null;

/* ── DOM refs ───────────────────────────────────────────────────────── */
const bubbleLayer  = document.getElementById("bubble-layer");
const imagePanel   = document.getElementById("image-panel");
const commentPanel = document.getElementById("uw-comment-panel");
const essaySlot    = document.getElementById("image-panel-essay");

/* ══════════════════════════════════════════════════════════════════════
   EVENT HOOKS FROM initial-local.js
   ══════════════════════════════════════════════════════════════════════ */

document.addEventListener("uwExhibitSelect", ev => {
  currentExhibit = ev.detail.exhibit;
  _clearOrbit();
  _buildPanel(currentExhibit);
  // Wait for image panel entrance animation, then begin orbit
  setTimeout(() => {
    if (currentExhibit) fetchAndOrbit(currentExhibit);
  }, 480);
});

document.addEventListener("uwExhibitDeselect", () => {
  currentExhibit = null;
  _clearOrbit();
  _hideCommentPanel();
});

/* ══════════════════════════════════════════════════════════════════════
   COMMENT PANEL — right-side form
   ══════════════════════════════════════════════════════════════════════ */

function _buildPanel(exhibit) {
  if (!commentPanel) return;

  // Title
  const titleEl = document.getElementById("uwcp-title");
  if (titleEl) titleEl.textContent = exhibit.name || "";

  // Voice count (loaded async)
  const voiceTextEl = document.getElementById("uwcp-voice-text");
  if (voiceTextEl) voiceTextEl.textContent = "loading…";

  // Build tag buttons
  const tagsEl = document.getElementById("uwcp-tags");
  if (tagsEl) {
    tagsEl.innerHTML = TAGS.map(t => `
      <button type="button" class="uwcp-tag" data-starter="${escHtml(t.starter)}" title="${escHtml(t.starter)}">
        <span class="uwcp-tag-icon" aria-hidden="true">${t.icon}</span>${escHtml(t.label)}
      </button>`).join("");

    tagsEl.querySelectorAll(".uwcp-tag").forEach(btn => {
      btn.addEventListener("click", () => {
        const ta = document.getElementById("uwcp-body");
        if (!ta) return;
        // Toggle: click same tag again → clear
        const isActive = btn.classList.contains("active");
        tagsEl.querySelectorAll(".uwcp-tag").forEach(b => b.classList.remove("active"));
        if (isActive) {
          ta.value = "";
        } else {
          btn.classList.add("active");
          ta.value = btn.dataset.starter;
          ta.setSelectionRange(ta.value.length, ta.value.length);
        }
        ta.focus();
        _validateSubmit();
      });
    });
  }

  // Wire textarea + submit
  const ta  = document.getElementById("uwcp-body");
  const sub = document.getElementById("uwcp-submit");
  if (ta)  ta.addEventListener("input", _validateSubmit);
  if (sub) sub.addEventListener("click", () => {
    const eid = String(exhibit.exhibitId || exhibit.id);
    _submitComment(eid, exhibit.color);
  });

  // Reset compose area
  if (ta)  ta.value = "";
  const name = document.getElementById("uwcp-name");
  if (name) name.value = "";
  const msg = document.getElementById("uwcp-msg");
  if (msg) { msg.textContent = ""; msg.className = "uwcp-msg"; }
  _validateSubmit();

  // Show panel
  commentPanel.setAttribute("aria-hidden", "false");
  commentPanel.classList.add("on");

  // Fetch count (deferred)
  const eid = String(exhibit.exhibitId || exhibit.id);
  _fetchVoiceCount(eid);

  // Show minimal cue in the image panel essay slot
  if (essaySlot) {
    essaySlot.textContent = "";
    essaySlot.className   = "image-panel-essay uw-essay-quiet";
  }
}

function _hideCommentPanel() {
  if (!commentPanel) return;
  commentPanel.classList.remove("on");
  commentPanel.setAttribute("aria-hidden", "true");
  if (essaySlot) {
    essaySlot.textContent = "";
    essaySlot.className   = "image-panel-essay";
  }
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
    el.textContent = n === 0 ? "No impressions yet"
                   : n === 1 ? "1 impression"
                   : `${n} impressions`;
  } catch (_) {
    el.textContent = "server offline";
  }
}

async function _submitComment(exhibitId, accentColor) {
  const ta   = document.getElementById("uwcp-body");
  const name = document.getElementById("uwcp-name");
  const btn  = document.getElementById("uwcp-submit");
  const msg  = document.getElementById("uwcp-msg");
  if (!ta || !ta.value.trim()) return;
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`${UW_API}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        exhibitId,
        username: name?.value.trim() || "Anonymous",
        world:    "visitor",
        content:  ta.value.trim(),
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const comment = await res.json();

    // Feedback
    if (msg) {
      msg.textContent = "Recorded — your impression joins the constellation.";
      msg.className   = "uwcp-msg ok";
      setTimeout(() => { if (msg) { msg.textContent = ""; msg.className = "uwcp-msg"; } }, 4000);
    }

    // Reset form
    ta.value = "";
    if (name) name.value = "";
    document.querySelectorAll(".uwcp-tag").forEach(b => b.classList.remove("active"));
    _validateSubmit();

    // Immediately orbit the new comment
    const text = comment.content.slice(0, 72) + (comment.content.length > 72 ? "…" : "");
    _addOrbitBubble(text, accentColor || "#c4a882", true);

    // Refresh count
    await _fetchVoiceCount(exhibitId);

  } catch (err) {
    console.error(err);
    if (msg) {
      msg.textContent = "Server unreachable — is the API running on :3800?";
      msg.className   = "uwcp-msg err";
    }
    if (btn) btn.disabled = false;
  }
}

/* ══════════════════════════════════════════════════════════════════════
   ORBITING COMMENT BUBBLES
   ══════════════════════════════════════════════════════════════════════ */

async function fetchAndOrbit(exhibit) {
  const eid = String(exhibit.exhibitId || exhibit.id);
  let comments = [];
  try {
    const res = await fetch(`${UW_API}/comments?exhibitId=${encodeURIComponent(eid)}&limit=12`);
    if (res.ok) comments = await res.json();
  } catch (_) {}

  const PLACEHOLDERS = [
    "The first impression is yours.",
    "No words left here yet.",
    "This exhibit awaits a visitor's voice.",
  ];

  const texts = comments.length
    ? comments.map(c => c.content.slice(0, 68) + (c.content.length > 68 ? "…" : ""))
    : PLACEHOLDERS;

  const color = exhibit.color || "#c4a882";
  texts.forEach((text, i) => {
    const angle = (i / texts.length) * Math.PI * 2;
    _addOrbitBubble(text, color, false, angle);
  });

  _orbitTick();
}

function _addOrbitBubble(text, color, isNew = false, fixedAngle = null) {
  if (!bubbleLayer) return;
  const el = document.createElement("div");
  el.className = isNew ? "visitor-bubble new" : "visitor-bubble";
  el.textContent = text;
  el.style.setProperty("--wc", color);
  bubbleLayer.appendChild(el);

  const angle  = fixedAngle ?? (Math.random() * Math.PI * 2);
  const radius = 200 + Math.random() * 80;
  const speed  = (0.00016 + Math.random() * 0.00014) * (Math.random() < 0.5 ? 1 : -1);
  orbitBubbles.push({ el, angle, radius, speed, wobble: Math.random() * Math.PI * 2, born: performance.now() });
}

function _orbitTick() {
  if (!imagePanel) return;
  if (!imagePanel.classList.contains("on")) {
    animFrame = requestAnimationFrame(_orbitTick);
    return;
  }

  const r  = imagePanel.getBoundingClientRect();
  const cx = r.left + r.width  / 2;
  const cy = r.top  + r.height / 2;
  const t  = performance.now();

  orbitBubbles.forEach(b => {
    b.angle += b.speed;
    const age     = Math.min((t - b.born) / 800, 1);
    const wobbleY = Math.sin(t * 0.0009 + b.wobble) * 18;

    // Elliptical orbit — wider than tall
    const x = cx + Math.cos(b.angle) * b.radius;
    const y = cy + Math.sin(b.angle) * (b.radius * 0.38) + wobbleY;

    b.el.style.left      = `${x}px`;
    b.el.style.top       = `${y}px`;
    b.el.style.opacity   = String(age * 0.78);
    b.el.style.transform = `translate(-50%, -50%) scale(${0.90 + age * 0.10})`;
  });

  animFrame = requestAnimationFrame(_orbitTick);
}

function _clearOrbit() {
  cancelAnimationFrame(animFrame);
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
