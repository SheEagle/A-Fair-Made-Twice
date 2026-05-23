/* ── Unfinished World ─────────────────────────────────────────────────── */
"use strict";

const API = "http://localhost:3800/api";

/* ── Star canvas (same as main page) ─────────────────────────────────── */
(function initStars() {
  const canvas = document.getElementById("star-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let stars = [];

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }

  function buildStars(n = 280) {
    stars = Array.from({ length: n }, () => ({
      x: Math.random(),
      y: Math.random(),
      r: Math.random() * 1.2 + 0.2,
      a: Math.random(),
      spd: 0.0004 + Math.random() * 0.0006,
      phs: Math.random() * Math.PI * 2,
    }));
  }

  function drawStars(t) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const s of stars) {
      const alpha = s.a * (0.55 + 0.45 * Math.sin(t * s.spd + s.phs));
      ctx.beginPath();
      ctx.arc(s.x * canvas.width, s.y * canvas.height, s.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255,232,190,${alpha})`;
      ctx.fill();
    }
    requestAnimationFrame(drawStars);
  }

  resize();
  buildStars();
  window.addEventListener("resize", resize);
  requestAnimationFrame(drawStars);
})();

/* ── State ────────────────────────────────────────────────────────────── */
const state = {
  selectedExhibit: null,   // { id, exhibitId, name, type, color }
  world: "visitor",
  feedMode: "exhibit",     // "exhibit" | "recent"
  loading: false,
};

/* ── DOM refs ─────────────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const els = {
  search:     $("exhibit-search"),
  exList:     $("exhibit-list"),
  selExhibit: $("selected-exhibit"),
  voiceBtns:  document.querySelectorAll(".voice-btn"),
  nameInput:  $("comment-name"),
  bodyInput:  $("comment-body"),
  charCount:  $("char-count"),
  submitBtn:  $("submit-btn"),
  submitMsg:  $("submit-msg"),
  feedList:   $("feed-list"),
  feedTabs:   document.querySelectorAll(".ftab"),
  liveCount:  $("live-count"),
  placeholder: $("feed-placeholder"),
};

/* ── Exhibit search ───────────────────────────────────────────────────── */
const exhibits = window.EXHIBIT_LIST || [];

function filterExhibits(query) {
  const q = query.toLowerCase().trim();
  if (!q) return exhibits.slice(0, 30);
  return exhibits
    .filter(e =>
      e.name.toLowerCase().includes(q) ||
      (e.type  && e.type.toLowerCase().includes(q)) ||
      (e.country && e.country.toLowerCase().includes(q))
    )
    .slice(0, 30);
}

function renderExhibitList(items) {
  els.exList.innerHTML = "";
  if (!items.length) {
    els.exList.classList.remove("open");
    return;
  }
  items.forEach(e => {
    const div = document.createElement("div");
    div.className = "exlist-item";
    div.setAttribute("role", "option");
    div.dataset.id = e.id;
    div.innerHTML = `
      <span class="exlist-dot"  style="background:${e.color || "#888"}"></span>
      <span class="exlist-name">${escHtml(e.name)}</span>
      <span class="exlist-type">${escHtml(e.type || "")}</span>
    `;
    div.addEventListener("mousedown", ev => {
      ev.preventDefault();
      selectExhibit(e);
    });
    els.exList.appendChild(div);
  });
  els.exList.classList.add("open");
}

els.search.addEventListener("input", () => {
  const items = filterExhibits(els.search.value);
  renderExhibitList(items);
});
els.search.addEventListener("focus", () => {
  if (!state.selectedExhibit) {
    renderExhibitList(filterExhibits(els.search.value));
  }
});
els.search.addEventListener("blur", () => {
  setTimeout(() => els.exList.classList.remove("open"), 150);
});

// Keyboard navigation in list
els.search.addEventListener("keydown", ev => {
  if (!els.exList.classList.contains("open")) return;
  const items = els.exList.querySelectorAll(".exlist-item");
  const cur = els.exList.querySelector("[aria-selected='true']");
  if (ev.key === "ArrowDown") {
    ev.preventDefault();
    const next = cur ? (cur.nextElementSibling || items[0]) : items[0];
    if (cur) cur.removeAttribute("aria-selected");
    next && next.setAttribute("aria-selected", "true");
  } else if (ev.key === "ArrowUp") {
    ev.preventDefault();
    const prev = cur ? (cur.previousElementSibling || items[items.length - 1]) : items[items.length - 1];
    if (cur) cur.removeAttribute("aria-selected");
    prev && prev.setAttribute("aria-selected", "true");
  } else if (ev.key === "Enter") {
    ev.preventDefault();
    if (cur) cur.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
  } else if (ev.key === "Escape") {
    els.exList.classList.remove("open");
  }
});

function selectExhibit(e) {
  state.selectedExhibit = e;
  els.search.value = "";
  els.exList.classList.remove("open");

  // Show badge
  els.selExhibit.innerHTML = `
    <span class="sel-dot" style="background:${e.color || "#888"}"></span>
    <span class="sel-name">${escHtml(e.name)}</span>
    <span class="sel-type">${escHtml(e.type || "")}</span>
    <button class="sel-clear" aria-label="Clear selection" title="Clear">×</button>
  `;
  els.selExhibit.classList.add("visible");
  els.selExhibit.querySelector(".sel-clear").addEventListener("click", clearExhibit);

  validateForm();
  if (state.feedMode === "exhibit") loadFeed();
}

function clearExhibit() {
  state.selectedExhibit = null;
  els.selExhibit.classList.remove("visible");
  els.selExhibit.innerHTML = "";
  validateForm();
  showFeedPlaceholder("Select an exhibit to see what others wrote.");
}

/* ── Voice selector ───────────────────────────────────────────────────── */
els.voiceBtns.forEach(btn => {
  btn.addEventListener("click", () => {
    els.voiceBtns.forEach(b => { b.classList.remove("active"); b.setAttribute("aria-pressed", "false"); });
    btn.classList.add("active");
    btn.setAttribute("aria-pressed", "true");
    state.world = btn.dataset.world;
  });
});

/* ── Char counter ─────────────────────────────────────────────────────── */
els.bodyInput.addEventListener("input", () => {
  const n = els.bodyInput.value.length;
  els.charCount.textContent = `${n} / 2000`;
  validateForm();
});

function validateForm() {
  const ok = state.selectedExhibit && els.bodyInput.value.trim().length >= 2;
  els.submitBtn.disabled = !ok;
}

/* ── Submit ───────────────────────────────────────────────────────────── */
els.submitBtn.addEventListener("click", async () => {
  if (!state.selectedExhibit) return;
  const content = els.bodyInput.value.trim();
  if (!content) return;

  els.submitBtn.disabled = true;
  setMsg("", "");

  try {
    const res = await fetch(`${API}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        exhibitId: String(state.selectedExhibit.exhibitId || state.selectedExhibit.id),
        username:  els.nameInput.value.trim() || "Anonymous",
        world:     state.world,
        content,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const comment = await res.json();

    setMsg("Your impression has been recorded.", "ok");
    els.bodyInput.value = "";
    els.charCount.textContent = "0 / 2000";

    // Prepend new comment to feed if showing this exhibit
    if (state.feedMode === "exhibit") {
      prependComment(comment, state.selectedExhibit);
    }
    await updateLiveCount();
  } catch (err) {
    console.error(err);
    setMsg("Could not reach the server. Is the API running?", "err");
    els.submitBtn.disabled = false;
  }
});

function setMsg(text, cls) {
  els.submitMsg.textContent = text;
  els.submitMsg.className = "submit-msg" + (cls ? ` ${cls}` : "");
}

/* ── Feed tabs ────────────────────────────────────────────────────────── */
els.feedTabs.forEach(tab => {
  tab.addEventListener("click", () => {
    els.feedTabs.forEach(t => { t.classList.remove("active"); t.setAttribute("aria-selected", "false"); });
    tab.classList.add("active");
    tab.setAttribute("aria-selected", "true");
    state.feedMode = tab.dataset.feed;
    loadFeed();
  });
});

/* ── Load feed ────────────────────────────────────────────────────────── */
async function loadFeed() {
  if (state.feedMode === "exhibit" && !state.selectedExhibit) {
    showFeedPlaceholder("Select an exhibit to see what others wrote.");
    return;
  }

  showSpinner();
  try {
    let rows, exhibitsById;
    if (state.feedMode === "exhibit") {
      const exhibitId = String(state.selectedExhibit.exhibitId || state.selectedExhibit.id);
      const res = await fetch(`${API}/comments?exhibitId=${encodeURIComponent(exhibitId)}`);
      if (!res.ok) throw new Error(await res.text());
      rows = await res.json();
      exhibitsById = null;
    } else {
      const res = await fetch(`${API}/recent?limit=40`);
      if (!res.ok) throw new Error(await res.text());
      rows = await res.json();
      // Build lookup for exhibit names in recent mode
      exhibitsById = {};
      exhibits.forEach(e => { exhibitsById[String(e.exhibitId || e.id)] = e; });
    }

    renderFeed(rows, exhibitsById);
    await updateLiveCount();
  } catch (err) {
    console.error(err);
    showFeedPlaceholder("Could not load comments. Is the API running on localhost:3800?");
  }
}

function renderFeed(rows, exhibitsById) {
  if (!rows.length) {
    showFeedPlaceholder("No impressions yet. Be the first to write one.");
    return;
  }
  els.feedList.innerHTML = "";
  rows.forEach(r => {
    const ex = exhibitsById ? exhibitsById[String(r.exhibit_id)] : state.selectedExhibit;
    prependComment(r, ex, false);
  });
}

function prependComment(c, ex, prepend = true) {
  // Remove placeholder if present
  const ph = els.feedList.querySelector(".feed-empty");
  if (ph) ph.remove();

  const div = document.createElement("div");
  div.className = "comment-card";
  const timeStr = formatTime(new Date(c.created_at));
  const exName  = ex ? escHtml(ex.name) : escHtml(String(c.exhibit_id));
  const exColor = ex ? (ex.color || "#888") : "#888";

  div.innerHTML = `
    <div class="cc-meta">
      <span class="cc-name">${escHtml(c.username || "Anonymous")}</span>
      <span class="cc-time">${timeStr}</span>
    </div>
    <span class="cc-world" data-world="${escHtml(c.world || "visitor")}">${escHtml(c.world || "visitor")}</span>
    <p class="cc-body">${escHtml(c.content)}</p>
    ${state.feedMode === "recent" ? `<div class="cc-exhibit"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${exColor};margin-right:5px;vertical-align:middle"></span>${exName}</div>` : ""}
  `;

  if (prepend && els.feedList.firstChild) {
    els.feedList.insertBefore(div, els.feedList.firstChild);
  } else {
    els.feedList.appendChild(div);
  }
}

function showFeedPlaceholder(msg) {
  els.feedList.innerHTML = `<div class="feed-empty">${escHtml(msg)}</div>`;
}

function showSpinner() {
  els.feedList.innerHTML = `<div class="feed-spinner"></div>`;
}

/* ── Live count ───────────────────────────────────────────────────────── */
async function updateLiveCount() {
  try {
    const res = await fetch(`${API}/recent?limit=1`);
    if (!res.ok) return;
    const rows = await res.json();
    if (rows.length) {
      els.liveCount.textContent = "Last impression: " + formatTime(new Date(rows[0].created_at));
    }
  } catch (_) {}
}

/* ── Utils ────────────────────────────────────────────────────────────── */
function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatTime(date) {
  const now  = Date.now();
  const diff = now - date.getTime();
  if (diff < 60_000)  return "just now";
  if (diff < 3_600_000) return Math.floor(diff / 60_000) + "m ago";
  if (diff < 86_400_000) return Math.floor(diff / 3_600_000) + "h ago";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/* ── Init ─────────────────────────────────────────────────────────────── */
updateLiveCount();
// Show recent by default when no exhibit selected
loadFeed();
// Periodically refresh recent tab
setInterval(() => {
  if (state.feedMode === "recent") loadFeed();
}, 30_000);
