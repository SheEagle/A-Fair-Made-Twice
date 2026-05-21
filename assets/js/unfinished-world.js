/* ──────────────────────────────────────────────────────────────────────
   unfinished-world.js
   Handles the Unfinished World layer: visitor comment bubbles that orbit
   the image panel, and the in-panel quick-tag comment form.
   Wired to initial-local.js via CustomEvents:
     "uwExhibitSelect"   { detail: { exhibit, index } }
     "uwExhibitDeselect"
   ────────────────────────────────────────────────────────────────────── */
"use strict";

const UW_API = "http://localhost:3800/api";

/* ── HCI tag palette ────────────────────────────────────────────────────
   Each tag has:
     label   — button text
     starter — sentence fragment pre-filled into textarea
     emoji   — small unicode icon (no colour emoji, just shape/symbol)
   ─────────────────────────────────────────────────────────────────────── */
const TAGS = [
  { label: "Wonder",     emoji: "✦", starter: "What struck me with wonder was " },
  { label: "Unease",     emoji: "◈", starter: "There was something unsettling here — " },
  { label: "Familiar",   emoji: "◎", starter: "This reminded me of " },
  { label: "Overlooked", emoji: "△", starter: "Most visitors seemed to miss " },
  { label: "Haunting",   emoji: "◇", starter: "I couldn’t quite forget " },
  { label: "Ordinary",   emoji: "○", starter: "What surprised me was how ordinary " },
  { label: "Grand",      emoji: "◉", starter: "The scale of it felt " },
  { label: "Personal",   emoji: "◑", starter: "Standing here, I thought of " },
];

/* ── State ──────────────────────────────────────────────────────────── */
let currentExhibit  = null;
let orbitTimer      = null;
let orbitBubbles    = [];       // { el, angle, radius, speed, wobble }
let animFrame       = null;

/* ── DOM refs ───────────────────────────────────────────────────────── */
const bubbleLayer = document.getElementById("bubble-layer");
const imagePanel  = document.getElementById("image-panel");
const essaySlot   = document.getElementById("image-panel-essay");

/* ── Listen for events from initial-local.js ────────────────────────── */
document.addEventListener("uwExhibitSelect", ev => {
  currentExhibit = ev.detail.exhibit;
  clearAll();
  // Wait for panel to animate in before fetching
  setTimeout(() => {
    if (currentExhibit) {
      buildForm(currentExhibit);
      fetchAndOrbit(currentExhibit);
    }
  }, 500);
});

document.addEventListener("uwExhibitDeselect", () => {
  currentExhibit = null;
  clearAll();
});

/* ── Clear all visitor UI ───────────────────────────────────────────── */
function clearAll() {
  cancelAnimationFrame(animFrame);
  clearInterval(orbitTimer);
  orbitBubbles.forEach(b => b.el.remove());
  orbitBubbles = [];
  if (essaySlot) essaySlot.innerHTML = "";
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

  // Always start orbiting; use placeholders if no comments yet
  spawnOrbitBubbles(comments, exhibit.color || "#c4a882");
}

function spawnOrbitBubbles(comments, accentColor) {
  if (!imagePanel || !bubbleLayer) return;

  const PLACEHOLDER = [
    "No words left here yet.",
    "The first impression is yours to record.",
    "This exhibit awaits a visitor's voice.",
  ];

  // Use real comments or placeholders
  const texts = comments.length
    ? comments.map(c => c.content.slice(0, 72) + (c.content.length > 72 ? "…" : ""))
    : PLACEHOLDER;

  // Create DOM elements
  texts.forEach((text, i) => {
    const el = document.createElement("div");
    el.className = "visitor-bubble";
    el.textContent = text;
    el.style.setProperty("--wc", accentColor);
    bubbleLayer.appendChild(el);

    // Space bubbles evenly around a full orbit
    const angle  = (i / texts.length) * Math.PI * 2 + (Math.random() * 0.4 - 0.2);
    const radius = 180 + Math.random() * 70;
    const speed  = (0.00018 + Math.random() * 0.00012) * (Math.random() < 0.5 ? 1 : -1);
    const wobble = Math.random() * Math.PI * 2;

    orbitBubbles.push({ el, angle, radius, speed, wobble, born: performance.now() });
  });

  orbitTick();
}

function orbitTick() {
  if (!imagePanel || !imagePanel.classList.contains("on")) {
    animFrame = requestAnimationFrame(orbitTick);
    return;
  }

  const r   = imagePanel.getBoundingClientRect();
  const cx  = r.left + r.width  / 2;
  const cy  = r.top  + r.height / 2;
  const now = performance.now();

  orbitBubbles.forEach(b => {
    b.angle += b.speed;
    const age = Math.min((now - b.born) / 900, 1);   // fade-in over 900 ms
    const wobbleY = Math.sin(now * 0.0008 + b.wobble) * 14;

    const x = cx + Math.cos(b.angle) * b.radius;
    const y = cy + Math.sin(b.angle) * (b.radius * 0.42) + wobbleY;

    b.el.style.left    = `${x}px`;
    b.el.style.top     = `${y}px`;
    b.el.style.opacity = String(age * 0.82);
    b.el.style.transform = `translate(-50%, -50%) scale(${0.88 + age * 0.12})`;
  });

  animFrame = requestAnimationFrame(orbitTick);
}

/* ══════════════════════════════════════════════════════════════════════
   IN-PANEL COMMENT FORM
   ══════════════════════════════════════════════════════════════════════ */

function buildForm(exhibit) {
  if (!essaySlot) return;
  const eid = String(exhibit.exhibitId || exhibit.id);

  essaySlot.innerHTML = `
    <div class="uw-inline-form" id="uw-inline-form">

      <div class="uw-voice-count" id="uw-voice-count">
        <span class="uvc-dot"></span><span id="uvc-text">loading voices…</span>
      </div>

      <div class="uw-tag-row" role="group" aria-label="Choose a register">
        ${TAGS.map(t => `
          <button type="button" class="uw-tag" data-starter="${escHtml(t.starter)}"
                  title="${escHtml(t.starter)}">
            <span class="uw-tag-icon" aria-hidden="true">${t.emoji}</span>
            ${escHtml(t.label)}
          </button>`).join("")}
      </div>

      <div class="uw-compose" id="uw-compose">
        <textarea id="uw-body" class="uw-textarea"
                  placeholder="Leave an impression…"
                  maxlength="2000" rows="3"
                  aria-label="Your impression"></textarea>
        <div class="uw-compose-row">
          <input id="uw-name" class="uw-name-input"
                 type="text" placeholder="Your name · optional"
                 maxlength="80" autocomplete="off">
          <button id="uw-submit" class="uw-submit-btn" disabled>Record</button>
        </div>
        <div id="uw-msg" class="uw-msg" aria-live="polite"></div>
      </div>

    </div>
  `;

  // Fetch count
  fetchVoiceCount(eid);

  // Tag click → pre-fill textarea and focus
  essaySlot.querySelectorAll(".uw-tag").forEach(btn => {
    btn.addEventListener("click", () => {
      const starter = btn.dataset.starter;
      const ta = document.getElementById("uw-body");
      if (!ta) return;
      // toggle: if already starts with this starter, clear it
      if (ta.value.startsWith(starter)) {
        ta.value = "";
      } else {
        ta.value = starter;
        ta.setSelectionRange(ta.value.length, ta.value.length);
      }
      // mark active tag
      essaySlot.querySelectorAll(".uw-tag").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      ta.focus();
      validateSubmit();
    });
  });

  // char validation
  const body = document.getElementById("uw-body");
  if (body) body.addEventListener("input", validateSubmit);

  // submit
  const submitBtn = document.getElementById("uw-submit");
  if (submitBtn) submitBtn.addEventListener("click", () => submitComment(eid, exhibit.color));
}

function validateSubmit() {
  const body = document.getElementById("uw-body");
  const btn  = document.getElementById("uw-submit");
  if (!body || !btn) return;
  btn.disabled = body.value.trim().length < 2;
}

async function fetchVoiceCount(exhibitId) {
  const el = document.getElementById("uvc-text");
  if (!el) return;
  try {
    const res = await fetch(`${UW_API}/comments?exhibitId=${encodeURIComponent(exhibitId)}&limit=200`);
    if (!res.ok) return;
    const rows = await res.json();
    const n = rows.length;
    el.textContent = n === 0 ? "No impressions yet — be the first"
                   : n === 1 ? "1 impression recorded"
                   : `${n} impressions recorded`;
  } catch (_) {
    el.textContent = "Server offline";
  }
}

async function submitComment(exhibitId, accentColor) {
  const body    = document.getElementById("uw-body");
  const nameEl  = document.getElementById("uw-name");
  const btn     = document.getElementById("uw-submit");
  const msg     = document.getElementById("uw-msg");

  if (!body || !body.value.trim()) return;
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`${UW_API}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        exhibitId,
        username: nameEl?.value.trim() || "Anonymous",
        world:    "visitor",
        content:  body.value.trim(),
      }),
    });

    if (!res.ok) throw new Error(await res.text());
    const comment = await res.json();

    // Show gentle confirmation
    if (msg) {
      msg.textContent = "Recorded. Your impression joins the constellation.";
      msg.className = "uw-msg ok";
    }

    // Reset form
    body.value = "";
    document.querySelectorAll(".uw-tag").forEach(b => b.classList.remove("active"));
    validateSubmit();

    // Add new bubble to orbit immediately
    const text = comment.content.slice(0, 72) + (comment.content.length > 72 ? "…" : "");
    if (bubbleLayer) {
      const el = document.createElement("div");
      el.className = "visitor-bubble new";
      el.textContent = text;
      el.style.setProperty("--wc", accentColor || "#c4a882");
      bubbleLayer.appendChild(el);

      const angle  = Math.random() * Math.PI * 2;
      const radius = 190 + Math.random() * 60;
      const speed  = 0.00020 * (Math.random() < 0.5 ? 1 : -1);
      orbitBubbles.push({ el, angle, radius, speed, wobble: Math.random() * Math.PI * 2, born: performance.now() });
    }

    // Refresh count
    await fetchVoiceCount(exhibitId);

    // Clear message after 4s
    setTimeout(() => { if (msg) { msg.textContent = ""; msg.className = "uw-msg"; } }, 4000);

  } catch (err) {
    console.error(err);
    if (msg) {
      msg.textContent = "Could not reach server. Is the API running?";
      msg.className = "uw-msg err";
    }
    if (btn) btn.disabled = false;
  }
}

/* ── Utility ────────────────────────────────────────────────────────── */
function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
