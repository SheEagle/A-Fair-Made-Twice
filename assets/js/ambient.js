"use strict";
/* ── Ambient sound manager ─────────────────────────────────────────────────
   Plays looping background tracks during constellation exploration.
   Rules:
     • Starts when a world is entered (body[data-world] changes)
     • Fades out when any exhibit is selected (image-panel gets .on)
     • Fades back in when exhibit is deselected
     • No ambient for the Unfinished World (silence is intentional)
     • A small mute toggle sits in the corner; state persists in sessionStorage
   ─────────────────────────────────────────────────────────────────────── */

const TRACKS = {
  official: [1,2,3,4].map(n => `./assets/ambient/official/${n}.mp3`),
  staged:   [1,2,3,4].map(n => `./assets/ambient/staged/${n}.mp3`),
  lived:    [1,2,3,4].map(n => `./assets/ambient/lived/${n}.mp3`),
};

const TARGET_VOL  = 0.30;   // master volume during exploration
const FADE_IN_MS  = 2200;
const FADE_OUT_MS = 900;

/* ── State ──────────────────────────────────────────────────────────── */
let activeWorld   = null;
let trackIdx      = 0;
let audio         = null;
let fadeRaf       = null;
let exhibitOpen   = false;
let muted         = sessionStorage.getItem("ambientMuted") === "1";

/* ── Mute toggle button ─────────────────────────────────────────────── */
const btn = document.createElement("button");
btn.id = "ambient-toggle";
btn.setAttribute("aria-label", muted ? "Unmute ambient sound" : "Mute ambient sound");
btn.innerHTML = _svgIcon(!muted);
document.body.appendChild(btn);

btn.addEventListener("click", () => {
  muted = !muted;
  sessionStorage.setItem("ambientMuted", muted ? "1" : "0");
  btn.setAttribute("aria-label", muted ? "Unmute ambient sound" : "Mute ambient sound");
  btn.innerHTML = _svgIcon(!muted);
  if (muted) {
    _fadeTo(0, FADE_OUT_MS);
  } else if (!exhibitOpen && activeWorld) {
    _ensurePlaying();
    _fadeTo(TARGET_VOL, FADE_IN_MS);
  }
});

function _svgIcon(soundOn) {
  if (soundOn) return `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
    <path d="M3 7.5h2.5L9 4v12l-3.5-3.5H3z"/>
    <path d="M12 7a3 3 0 0 1 0 6"/><path d="M14 4.5a6 6 0 0 1 0 11"/>
  </svg>`;
  return `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
    <path d="M3 7.5h2.5L9 4v12l-3.5-3.5H3z"/>
    <line x1="14" y1="7" x2="18" y2="13"/><line x1="18" y1="7" x2="14" y2="13"/>
  </svg>`;
}

/* ── Audio engine ───────────────────────────────────────────────────── */
function _ensurePlaying() {
  if (!activeWorld || !TRACKS[activeWorld]) return;
  if (!audio) {
    audio = new Audio();
    audio.volume = 0;
    audio.addEventListener("ended", _nextTrack);
  }
  if (audio.paused) {
    audio.src = TRACKS[activeWorld][trackIdx % TRACKS[activeWorld].length];
    audio.play().catch(() => {});
  }
}

function _nextTrack() {
  if (!activeWorld || !TRACKS[activeWorld]) return;
  trackIdx = (trackIdx + 1) % TRACKS[activeWorld].length;
  audio.src = TRACKS[activeWorld][trackIdx];
  audio.volume = muted || exhibitOpen ? 0 : TARGET_VOL;
  audio.play().catch(() => {});
}

function _fadeTo(target, ms) {
  if (!audio) return;
  if (fadeRaf) cancelAnimationFrame(fadeRaf);
  const start     = audio.volume;
  const startTime = performance.now();
  function step(now) {
    const t = Math.min((now - startTime) / ms, 1);
    const ease = t < 0.5 ? 2*t*t : -1+(4-2*t)*t;   // ease-in-out
    audio.volume = start + (target - start) * ease;
    if (t < 1) {
      fadeRaf = requestAnimationFrame(step);
    } else {
      fadeRaf = null;
      if (target === 0) audio.pause();
    }
  }
  if (target > 0 && audio.paused) {
    _ensurePlaying();
  }
  fadeRaf = requestAnimationFrame(step);
}

function _switchWorld(world) {
  if (world === activeWorld) return;
  activeWorld = world;

  if (!TRACKS[world]) {
    // unfinished world or none — fade to silence
    if (audio && !audio.paused) _fadeTo(0, FADE_OUT_MS);
    return;
  }

  // start at a random track offset when entering a new world
  trackIdx = Math.floor(Math.random() * TRACKS[world].length);

  if (audio && !audio.paused) {
    // brief fade-out → swap track → fade back in
    _fadeTo(0, FADE_OUT_MS);
    setTimeout(() => {
      if (!audio) return;
      audio.src = TRACKS[world][trackIdx];
      if (!muted && !exhibitOpen) {
        audio.play().catch(() => {});
        _fadeTo(TARGET_VOL, FADE_IN_MS);
      }
    }, FADE_OUT_MS + 80);
  } else {
    if (!muted && !exhibitOpen) {
      _ensurePlaying();
      _fadeTo(TARGET_VOL, FADE_IN_MS);
    }
  }
}

function _onExhibitOpen() {
  exhibitOpen = true;
  if (audio && !audio.paused) _fadeTo(0, FADE_OUT_MS);
}

function _onExhibitClose() {
  exhibitOpen = false;
  if (!muted && activeWorld && TRACKS[activeWorld]) {
    _ensurePlaying();
    _fadeTo(TARGET_VOL, FADE_IN_MS);
  }
}

/* ── Observers ──────────────────────────────────────────────────────── */

// World change: watch body[data-world]
new MutationObserver(() => {
  _switchWorld(document.body.dataset.world || null);
}).observe(document.body, { attributes: true, attributeFilter: ["data-world"] });

// Exhibit open/close: watch #image-panel class
const imagePanel = document.getElementById("image-panel");
if (imagePanel) {
  new MutationObserver(() => {
    if (imagePanel.classList.contains("on")) _onExhibitOpen();
    else _onExhibitClose();
  }).observe(imagePanel, { attributes: true, attributeFilter: ["class"] });
}

// Also hook unfinished-world custom events
document.addEventListener("uwExhibitSelect",   _onExhibitOpen);
document.addEventListener("uwExhibitDeselect", _onExhibitClose);
