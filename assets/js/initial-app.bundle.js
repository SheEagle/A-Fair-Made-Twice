(() => {
  "use strict";

  const DATA_DIR = "./outputs/mineru_triview_gemini_rerank_merge_full_v2";

  const WORLD_CONFIG = {
    official: {
      label: "The Official World",
      className: "official",
      colorHex: 0x8fb7ff,
      orbit: -0.12,
      scale: [1.08, 1.0, 1.0],
      offset: [0, 0, 0]
    },
    staged: {
      label: "The Staged World",
      className: "staged",
      colorHex: 0xd7a86e,
      orbit: 0.72,
      scale: [1.02, 0.92, 1.08],
      offset: [2.65, 0.25, -1.1]
    },
    lived: {
      label: "The Lived World",
      className: "lived",
      colorHex: 0xff8ea8,
      orbit: -0.76,
      scale: [0.98, 1.08, 1.02],
      offset: [-2.55, -0.15, 0.95]
    }
  };

  const WORLD_TO_DATASET = {
    official: "official",
    staged: "institutional",
    lived: "personal"
  };

  const DATASET_TO_WORLD = {
    official: "official",
    institutional: "staged",
    staged: "staged",
    personal: "lived",
    lived: "lived"
  };

  const VIEW_ALIASES = {
    overall: "overall",
    technical: "technical",
    made: "technical",
    category: "category",
    is: "category",
    exhibition: "exhibition",
    belongs: "exhibition",
    perception: "perception",
    seen: "perception"
  };

  const VIEWS = ["overall", "technical", "category", "exhibition", "perception"];

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function wrap360(value) {
    const twoPi = Math.PI * 2;
    while (value < 0) value += twoPi;
    while (value >= twoPi) value -= twoPi;
    return value;
  }

  function normalizeKey(value) {
    return String(value ?? "").trim().toLowerCase().replace(/\s+/g, "_");
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function colorToCss(color, alpha = 1) {
    const r = Math.round(color.r * 255);
    const g = Math.round(color.g * 255);
    const b = Math.round(color.b * 255);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function projectVector(vector, camera) {
    const projected = vector.clone().project(camera);
    return {
      x: (projected.x * 0.5 + 0.5) * innerWidth,
      y: (-0.5 * projected.y + 0.5) * innerHeight,
      z: projected.z
    };
  }

  async function fetchText(path) {
    const response = await fetch(path);
    if (!response.ok) {
      throw new Error(`Cannot load ${path}: ${response.status} ${response.statusText}`);
    }
    return response.text();
  }

  function parseJsonl(text) {
    return text.split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => JSON.parse(line));
  }

  function parseCsv(text) {
    const rows = [];
    let row = [];
    let cell = "";
    let quoted = false;

    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      const next = text[i + 1];

      if (ch === '"' && quoted && next === '"') {
        cell += '"';
        i++;
        continue;
      }
      if (ch === '"') {
        quoted = !quoted;
        continue;
      }
      if (ch === "," && !quoted) {
        row.push(cell);
        cell = "";
        continue;
      }
      if ((ch === "\n" || ch === "\r") && !quoted) {
        if (ch === "\r" && next === "\n") i++;
        row.push(cell);
        if (row.some(v => v.trim() !== "")) rows.push(row);
        row = [];
        cell = "";
        continue;
      }
      cell += ch;
    }

    if (cell || row.length) {
      row.push(cell);
      if (row.some(v => v.trim() !== "")) rows.push(row);
    }

    if (!rows.length) return [];
    const headers = rows[0].map(h => h.trim());
    return rows.slice(1).map(values => {
      const obj = {};
      headers.forEach((h, i) => obj[h] = values[i] ?? "");
      return obj;
    });
  }

  function firstDefined(obj, keys) {
    for (const key of keys) {
      if (obj && obj[key] !== undefined && obj[key] !== null && obj[key] !== "") return obj[key];
    }
    return undefined;
  }

  function getExhibitId(row) {
    return String(firstDefined(row, [
      "product_id", "exhibit_id", "id", "profile_id", "object_id", "item_id", "index"
    ]) ?? "").trim();
  }

  function getExhibitName(row) {
    return String(firstDefined(row, [
      "name", "title", "product_name", "exhibit_name", "object_name", "label"
    ]) ?? "Untitled exhibit").trim();
  }

  function getWorld(row) {
    const raw = firstDefined(row, ["world", "discourse", "voice", "source_world", "embedding_world", "archive"]);
    return DATASET_TO_WORLD[normalizeKey(raw)] || "official";
  }

  function getView(row) {
    const raw = firstDefined(row, ["view", "field", "dimension", "aspect", "embedding_type", "analysis_type"]);
    return VIEW_ALIASES[normalizeKey(raw)] || "overall";
  }

  function getCoordinate(row, keys, fallback = 0) {
    const value = firstDefined(row, keys);
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
  }

  function getTextValue(row) {
    return String(firstDefined(row, [
      "text", "value", "summary", "quote", "content", "chunk", "description", "narrative"
    ]) ?? "").trim();
  }

  function extractProfileText(profile, view) {
    const candidates = [
      profile?.narratives?.[view],
      profile?.analysis?.[view],
      profile?.[view],
      profile?.[`text_${view}`],
      profile?.[`summary_${view}`],
      profile?.description,
      profile?.summary
    ];

    const result = [];
    for (const candidate of candidates) {
      if (!candidate) continue;
      if (Array.isArray(candidate)) {
        for (const item of candidate) {
          if (typeof item === "string") result.push({ key: view, val: item });
          else if (item && typeof item === "object") {
            result.push({ key: item.key || item.label || view, val: item.val || item.value || item.text || item.summary || "" });
          }
        }
      } else if (typeof candidate === "object") {
        Object.entries(candidate).forEach(([key, val]) => {
          if (typeof val === "string") result.push({ key, val });
        });
      } else if (typeof candidate === "string") {
        result.push({ key: view, val: candidate });
      }
    }
    return result.filter(item => item.val);
  }

  function normalizeProfile(row, index) {
    const id = getExhibitId(row) || String(index);
    return {
      id,
      sourceIndex: index,
      name: getExhibitName(row),
      country: firstDefined(row, ["country", "nation", "section", "origin"]) || "",
      type: firstDefined(row, ["type", "category", "object_type", "class"]) || "",
      location: firstDefined(row, ["location", "place", "site"]) || "",
      raw: row,
      narratives: { official: {}, staged: {}, lived: {} },
      pos: { official: {}, staged: {}, lived: {} },
      similar: { official: {}, staged: {}, lived: {} }
    };
  }

  function addNarrativeFromEmbedding(exhibit, world, view, row) {
    const text = getTextValue(row);
    if (!text) return;
    exhibit.narratives[world][view] ||= [];
    exhibit.narratives[world][view].push({ key: view, val: text });
  }

  function addProfileFallbackNarratives(exhibit) {
    for (const world of ["official", "staged", "lived"]) {
      for (const view of VIEWS) {
        if (exhibit.narratives[world][view]?.length) continue;
        const fallback = extractProfileText(exhibit.raw, view);
        if (fallback.length) exhibit.narratives[world][view] = fallback;
      }
    }
  }

  function readSimilarityRows(rows, idToIndex) {
    const result = new Map();

    for (const row of rows) {
      const sourceId = String(firstDefined(row, ["source_id", "id1", "from", "product_id", "exhibit_id", "query_id"]) ?? "").trim();
      const targetId = String(firstDefined(row, ["target_id", "id2", "to", "similar_id", "neighbor_id"]) ?? "").trim();
      if (!sourceId || !targetId || !idToIndex.has(sourceId) || !idToIndex.has(targetId)) continue;

      const world = DATASET_TO_WORLD[normalizeKey(firstDefined(row, ["world", "discourse", "voice"]))] || "official";
      const view = VIEW_ALIASES[normalizeKey(firstDefined(row, ["view", "field", "dimension", "aspect"]))] || "overall";
      const score = Number(firstDefined(row, ["score", "similarity", "cosine", "value"]) ?? 0);

      const key = `${sourceId}|${world}|${view}`;
      if (!result.has(key)) result.set(key, []);
      result.get(key).push({
        targetIndex: idToIndex.get(targetId),
        score: Number.isFinite(score) ? score : 0,
        reason: String(firstDefined(row, ["reason", "explanation", "why"]) ?? "")
      });
    }

    for (const list of result.values()) list.sort((a, b) => b.score - a.score);
    return result;
  }

  function fillSimilarityFromMatrix(exhibits, csvRows, idToIndex) {
    const edgeMap = readSimilarityRows(csvRows, idToIndex);
    for (const ex of exhibits) {
      for (const world of ["official", "staged", "lived"]) {
        for (const view of VIEWS) {
          const key = `${ex.id}|${world}|${view}`;
          const matches = edgeMap.get(key) || edgeMap.get(`${ex.id}|official|overall`) || [];
          ex.similar[world][view] = matches.slice(0, 8).map(item => item.targetIndex);
        }
      }
    }
  }

  function fillSimilarityFromDistance(exhibits) {
    for (const world of ["official", "staged", "lived"]) {
      for (const view of VIEWS) {
        for (const ex of exhibits) {
          if (ex.similar[world][view]?.length) continue;
          const source = ex.pos[world][view] || ex.pos[world].overall;
          if (!source) continue;
          ex.similar[world][view] = exhibits
            .map((other, idx) => {
              const target = other.pos[world][view] || other.pos[world].overall;
              if (!target || other.id === ex.id) return null;
              const dx = source[0] - target[0];
              const dy = source[1] - target[1];
              const dz = source[2] - target[2];
              return { idx, d: dx * dx + dy * dy + dz * dz };
            })
            .filter(Boolean)
            .sort((a, b) => a.d - b.d)
            .slice(0, 8)
            .map(item => item.idx);
        }
      }
    }
  }

  async function loadExpoData(dataDir = DATA_DIR) {
    const [
      profilesText,
      officialText,
      personalText,
      institutionalText,
      umapText,
      similarityText
    ] = await Promise.all([
      fetchText(`${dataDir}/exhibit_profiles.jsonl`),
      fetchText(`${dataDir}/exhibit_embeddings_official.jsonl`),
      fetchText(`${dataDir}/exhibit_embeddings_personal.jsonl`),
      fetchText(`${dataDir}/exhibit_embeddings_institutional.jsonl`),
      fetchText(`${dataDir}/umap_coordinates.jsonl`),
      fetchText(`${dataDir}/similarity_matrix.csv`).catch(() => "")
    ]);

    const profileRows = parseJsonl(profilesText);
    const exhibits = profileRows.map(normalizeProfile);
    const idToIndex = new Map(exhibits.map((ex, idx) => [ex.id, idx]));

    const embeddingBatches = [
      ["official", parseJsonl(officialText)],
      ["lived", parseJsonl(personalText)],
      ["staged", parseJsonl(institutionalText)]
    ];

    for (const [world, rows] of embeddingBatches) {
      for (const row of rows) {
        const id = getExhibitId(row);
        const idx = idToIndex.get(id);
        if (idx === undefined) continue;
        addNarrativeFromEmbedding(exhibits[idx], world, getView(row), row);
      }
    }

    const umapRows = parseJsonl(umapText);
    for (const row of umapRows) {
      const id = getExhibitId(row);
      const idx = idToIndex.get(id);
      if (idx === undefined) continue;
      const world = getWorld(row);
      const view = getView(row);
      exhibits[idx].pos[world][view] = [
        getCoordinate(row, ["x", "umap_x", "coord_x", "0"]),
        getCoordinate(row, ["y", "umap_y", "coord_y", "1"]),
        getCoordinate(row, ["z", "umap_z", "coord_z", "2"], 0)
      ];
    }

    for (const ex of exhibits) {
      for (const world of ["official", "staged", "lived"]) {
        if (!ex.pos[world].overall) {
          const views = Object.values(ex.pos[world]);
          if (views.length) ex.pos[world].overall = views[0];
        }
      }
      addProfileFallbackNarratives(ex);
    }

    if (similarityText.trim()) fillSimilarityFromMatrix(exhibits, parseCsv(similarityText), idToIndex);
    fillSimilarityFromDistance(exhibits);

    return exhibits;
  }

  function makeDemoData() {
    const names = [
      "Imperial Cannon", "Relief Globe", "Jacquard Loom", "Ceramic Tile", "Stereoscope",
      "Steam Engine", "Glass Pavilion", "Textile Sample", "Bronze Figure", "Scientific Instrument",
      "Printing Press", "Navigation Device", "Agricultural Machine", "Porcelain Vase", "Optical Apparatus"
    ];
    return names.map((name, i) => {
      const id = String(i);
      const ex = {
        id,
        name,
        country: ["France", "Britain", "Ottoman Empire", "Japan", "United States"][i % 5],
        type: ["Machine", "Display", "Craft", "Instrument"][i % 4],
        location: "Champ de Mars",
        narratives: { official: {}, staged: {}, lived: {} },
        pos: { official: {}, staged: {}, lived: {} },
        similar: { official: {}, staged: {}, lived: {} }
      };
      for (const world of ["official", "staged", "lived"]) {
        for (const view of VIEWS) {
          const a = (i / names.length) * Math.PI * 2 + (view.length * 0.1);
          ex.pos[world][view] = [Math.cos(a) * 2.4, Math.sin(a * 1.7) * 1.1, Math.sin(a) * 2.0];
          ex.narratives[world][view] = [
            { key: view, val: `${name} in the ${WORLD_CONFIG[world].label}: extracted discourse text will appear here when the JSONL data loads correctly.` },
            { key: "archive", val: "This is fallback demo text, not your real embedding output." }
          ];
          ex.similar[world][view] = [(i + 1) % names.length, (i + 2) % names.length, (i + 3) % names.length];
        }
      }
      return ex;
    });
  }

  const els = {
    host: document.getElementById("renderer-host"),
    labels: document.getElementById("label-root"),
    intro: document.getElementById("intro"),
    worldBar: document.getElementById("world-bar"),
    viewBar: document.getElementById("view-bar"),
    discBar: document.getElementById("disc-bar"),
    deselectHint: document.getElementById("deselect-hint"),
    tip: document.getElementById("tip"),
    tipName: document.getElementById("tip-name"),
    panel: document.getElementById("object-panel"),
    connector: document.getElementById("connector-canvas")
  };

  const state = {
    exhibits: [],
    meshes: [],
    targets: [],
    currentWorld: null,
    currentView: "overall",
    discourseMode: "focus",
    selectedIndex: -1,
    hoveredIndex: -1,
    camTheta: 0,
    camPhi: Math.PI * 0.45,
    camTargetTheta: 0,
    camTargetPhi: Math.PI * 0.45,
    camRadius: 8.6,
    camTargetRadius: 8.6,
    dragging: false,
    dragStart: { x: 0, y: 0 },
    dragMoved: false,
    labels: [],
    dataReady: false
  };

  let renderer, scene, camera, raycaster, pointer, stars, ctx;

  function showError(error) {
    let box = document.querySelector(".loading-error");
    if (!box) {
      box = document.createElement("div");
      box.className = "loading-error";
      document.body.appendChild(box);
    }
    box.innerHTML = `
      <strong>Real data loading failed, demo data is shown.</strong><br>
      ${escapeHtml(error.message)}<br><br>
      请确认：1）用 <code>python3 -m http.server 8000</code> 打开；
      2）<code>outputs/mineru_triview_gemini_rerank_merge_full_v2</code> 和 <code>initial.html</code> 在同一项目根目录下。
    `;
  }

  function setupThree() {
    if (!window.THREE) {
      throw new Error("THREE is not loaded. Check ./vendor/three.min.js path.");
    }

    WORLD_CONFIG.official.color = new THREE.Color(WORLD_CONFIG.official.colorHex);
    WORLD_CONFIG.staged.color = new THREE.Color(WORLD_CONFIG.staged.colorHex);
    WORLD_CONFIG.lived.color = new THREE.Color(WORLD_CONFIG.lived.colorHex);

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.setSize(innerWidth, innerHeight);
    renderer.setClearColor(0x04040e, 0);
    els.host.appendChild(renderer.domElement);

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(62, innerWidth / innerHeight, 0.1, 100);
    camera.position.set(0, 0, 8.6);

    raycaster = new THREE.Raycaster();
    pointer = new THREE.Vector2();
    ctx = els.connector.getContext("2d");
    resizeConnector();

    stars = makeStars();
  }

  function resizeConnector() {
    els.connector.width = innerWidth;
    els.connector.height = innerHeight;
  }

  function makeStars() {
    const count = 900;
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(count * 3);
    const col = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
      const r = 2.4 + Math.random() * 6.6;
      const a = Math.random() * Math.PI * 2;
      const b = Math.acos(2 * Math.random() - 1);
      pos[i * 3] = r * Math.sin(b) * Math.cos(a);
      pos[i * 3 + 1] = r * Math.sin(b) * Math.sin(a) * 0.72;
      pos[i * 3 + 2] = r * Math.cos(b);
      const v = 0.45 + Math.random() * 0.55;
      col[i * 3] = v;
      col[i * 3 + 1] = v * 0.86;
      col[i * 3 + 2] = v * 0.78;
    }

    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));

    const points = new THREE.Points(
      geo,
      new THREE.PointsMaterial({
        size: 0.025,
        vertexColors: true,
        transparent: true,
        opacity: 0.55,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      })
    );

    scene.add(points);
    return points;
  }

  function normalizePositions(exhibits) {
    const all = [];
    for (const ex of exhibits) {
      for (const world of Object.keys(WORLD_CONFIG)) {
        for (const view of VIEWS) {
          const p = ex.pos?.[world]?.[view];
          if (p) all.push(p);
        }
      }
    }
    if (!all.length) return;

    const mins = [Infinity, Infinity, Infinity];
    const maxs = [-Infinity, -Infinity, -Infinity];
    for (const p of all) {
      for (let i = 0; i < 3; i++) {
        mins[i] = Math.min(mins[i], p[i] ?? 0);
        maxs[i] = Math.max(maxs[i], p[i] ?? 0);
      }
    }

    const center = mins.map((m, i) => (m + maxs[i]) / 2);
    const span = Math.max(...mins.map((m, i) => maxs[i] - m), 1);

    for (const ex of exhibits) {
      for (const world of Object.keys(WORLD_CONFIG)) {
        for (const view of VIEWS) {
          const p = ex.pos?.[world]?.[view];
          if (!p) continue;
          p[0] = ((p[0] - center[0]) / span) * 4.8;
          p[1] = ((p[1] - center[1]) / span) * 4.8;
          p[2] = ((p[2] - center[2]) / span) * 4.8;
        }
      }
    }
  }

  function replaceData(exhibits) {
    clearLabels();
    for (const mesh of state.meshes) scene.remove(mesh);

    state.exhibits = exhibits;
    state.meshes = [];
    state.targets = [];
    normalizePositions(state.exhibits);
    makeMeshes();

    state.dataReady = true;
    if (state.currentWorld) applyLayout();
  }

  function makeMeshes() {
    state.exhibits.forEach((ex, i) => {
      const geometry = new THREE.SphereGeometry(0.065, 12, 12);
      const material = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.82 });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set((Math.random() - 0.5) * 6, (Math.random() - 0.5) * 4, (Math.random() - 0.5) * 5);
      mesh.userData.index = i;

      const halo = new THREE.Mesh(
        new THREE.SphereGeometry(0.14, 12, 12),
        new THREE.MeshBasicMaterial({
          color: 0xffffff,
          transparent: true,
          opacity: 0.02,
          blending: THREE.AdditiveBlending,
          depthWrite: false
        })
      );
      mesh.add(halo);
      mesh.userData.halo = halo;

      state.meshes.push(mesh);
      state.targets.push(mesh.position.clone());
      scene.add(mesh);
    });
  }

  function orbitTransform(world, p, i = 0) {
    const cfg = WORLD_CONFIG[world];
    const c = Math.cos(cfg.orbit);
    const s = Math.sin(cfg.orbit);
    const x = p[0] * cfg.scale[0];
    const y = p[1] * cfg.scale[1];
    const z = p[2] * cfg.scale[2];
    const jitterX = world === "lived" ? Math.cos(i * 1.7) * 0.07 : 0;
    const jitterY = world === "staged" ? Math.sin(i * 1.1) * 0.05 : 0;
    const jitterZ = world === "official" ? Math.sin(i * 0.6) * 0.04 : 0;
    return [x * c - z * s + cfg.offset[0] + jitterX, y + cfg.offset[1] + jitterY, x * s + z * c + cfg.offset[2] + jitterZ];
  }

  function getBasePosition(ex, world, view) {
    return ex.pos?.[world]?.[view] || ex.pos?.[world]?.overall || ex.pos?.official?.overall || [0, 0, 0];
  }

  function getNarratives(ex, world, view) {
    const scoped = ex.narratives?.[world] || {};
    const items = scoped[view] || [];
    if (view !== "overall" && items.length) return items;

    const gathered = [];
    for (const key of VIEWS) {
      const part = scoped[key] || [];
      if (part.length) gathered.push(...part.slice(0, key === "overall" ? 2 : 1));
    }
    return gathered.slice(0, 7);
  }

  function sourceWorld() {
    if (state.discourseMode !== "counterpoint") return state.currentWorld;
    if (state.currentWorld === "official") return "lived";
    if (state.currentWorld === "lived") return "official";
    return "official";
  }

  function activeColor() {
    return WORLD_CONFIG[state.currentWorld]?.color || new THREE.Color(0xffffff);
  }

  function setWorld(world) {
    state.currentWorld = world;
    state.selectedIndex = -1;
    state.hoveredIndex = -1;
    clearLabels();

    els.intro.classList.add("hidden");
    els.worldBar.classList.add("on");
    els.viewBar.classList.add("on");
    els.discBar.classList.add("on");
    els.deselectHint.classList.remove("on");
    els.panel.classList.remove("on");

    document.querySelectorAll(".wb").forEach(btn => btn.classList.toggle("active", btn.dataset.world === world));
    applyLayout();
  }

  function setView(view) {
    state.currentView = view;
    clearLabels();
    document.querySelectorAll(".vb").forEach(btn => btn.classList.toggle("active", btn.dataset.view === view));
    applyLayout();
    if (state.selectedIndex >= 0) selectExhibit(state.selectedIndex);
  }

  function applyLayout() {
    if (!state.currentWorld || !state.meshes.length) return;
    state.exhibits.forEach((ex, i) => {
      const base = getBasePosition(ex, state.currentWorld, state.currentView);
      const p = orbitTransform(state.currentWorld, base, i);
      state.targets[i].set(p[0], p[1], p[2]);
      state.meshes[i].material.color.copy(activeColor().clone().lerp(new THREE.Color(0xffffff), 0.18));
    });
  }

  function clearLabels() {
    for (const el of state.labels) el.remove();
    state.labels = [];
    if (ctx) ctx.clearRect(0, 0, innerWidth, innerHeight);
  }

  function updateChipAt(el, x, y) {
    el.style.left = `${clamp(x, 70, innerWidth - 70)}px`;
    el.style.top = `${clamp(y, 24, innerHeight - 24)}px`;
  }

  function updateCardAt(el, x, y) {
    el.style.left = `${clamp(x, 120, innerWidth - 120)}px`;
    el.style.top = `${clamp(y, 70, innerHeight - 70)}px`;
  }

  function selectExhibit(index) {
    if (index < 0 || !state.exhibits[index]) return;
    state.selectedIndex = index;
    state.hoveredIndex = index;
    clearLabels();

    const ex = state.exhibits[index];
    const world = sourceWorld();
    const view = state.currentView;
    const narratives = getNarratives(ex, world, view).slice(0, 7);

    narratives.forEach((item, i) => {
      const bubble = document.createElement("div");
      bubble.className = `kw-bubble ${WORLD_CONFIG[world].className}`;
      bubble.dataset.kind = "bubble";
      bubble.dataset.index = String(i);
      bubble.innerHTML = `<span class="bubble-field">${escapeHtml(item.key || view)}</span><span class="bubble-value">${escapeHtml(item.val || item.value || item.text || "")}</span>`;
      els.labels.appendChild(bubble);
      state.labels.push(bubble);
      requestAnimationFrame(() => bubble.classList.add("shown"));
    });

    const similar = ex.similar?.[state.currentWorld]?.[view] || ex.similar?.[state.currentWorld]?.overall || [];
    similar.slice(0, 3).forEach((targetIndex, i) => {
      const target = state.exhibits[targetIndex];
      if (!target) return;
      const card = document.createElement("button");
      card.type = "button";
      card.className = "sim-card";
      card.dataset.kind = "similar";
      card.dataset.index = String(i);
      card.innerHTML = `<div class="sim-card-label">Similar exhibit</div><div class="sim-card-name">${escapeHtml(target.name)}</div><div class="sim-card-reason">${escapeHtml(view)} / ${escapeHtml(WORLD_CONFIG[state.currentWorld].label)}</div>`;
      card.addEventListener("click", event => {
        event.stopPropagation();
        selectExhibit(targetIndex);
      });
      els.labels.appendChild(card);
      state.labels.push(card);
      requestAnimationFrame(() => card.classList.add("shown"));
    });

    renderPanel(ex, world, narratives);
    els.deselectHint.classList.add("on");
  }

  function renderPanel(ex, world, narratives) {
    els.panel.innerHTML = `
      <div class="panel-kicker">${escapeHtml(WORLD_CONFIG[world].label)} · ${escapeHtml(state.currentView)}</div>
      <h2 class="panel-title">${escapeHtml(ex.name)}</h2>
      <div class="panel-sub">${escapeHtml([ex.country, ex.type, ex.location].filter(Boolean).join(" / "))}</div>
      <div class="panel-essay">${escapeHtml(narratives[0]?.val || "No extracted text is available for this view.")}</div>
      <div class="panel-prompt">Click a similar exhibit card to jump. Switch world or view above to remap the same exhibit through another discourse.</div>
    `;
    els.panel.classList.add("on");
  }

  function deselect() {
    state.selectedIndex = -1;
    state.hoveredIndex = -1;
    clearLabels();
    els.panel.classList.remove("on");
    els.deselectHint.classList.remove("on");
    els.tip.style.opacity = "0";
  }

  function updateLabelPositions() {
    if (state.selectedIndex < 0 || !state.meshes[state.selectedIndex]) return;
    const origin = projectVector(state.meshes[state.selectedIndex].position, camera);
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    const col = activeColor();

    state.labels.forEach(el => {
      const kind = el.dataset.kind;
      const i = Number(el.dataset.index || 0);

      if (kind === "bubble") {
        const angle = -Math.PI / 2 + i * (Math.PI * 2 / 7);
        const radius = 145 + (i % 3) * 26;
        updateChipAt(el, origin.x + Math.cos(angle) * radius, origin.y + Math.sin(angle) * radius * 0.62);
      }

      if (kind === "similar") {
        const x = origin.x + 270;
        const y = origin.y - 110 + i * 92;
        updateCardAt(el, x, y);
        ctx.save();
        ctx.strokeStyle = colorToCss(col, 0.45);
        ctx.lineWidth = 1.2;
        ctx.setLineDash([4, 6]);
        ctx.beginPath();
        ctx.moveTo(origin.x, origin.y);
        ctx.lineTo(parseFloat(el.style.left) - 112, parseFloat(el.style.top));
        ctx.stroke();
        ctx.restore();
      }
    });
  }

  function updateHoverFromPointer(event) {
    if (!state.currentWorld || state.dragging) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(state.meshes, false);

    if (hits.length) {
      const index = hits[0].object.userData.index;
      state.hoveredIndex = index;
      els.tipName.textContent = state.exhibits[index].name;
      els.tip.style.left = `${event.clientX + 14}px`;
      els.tip.style.top = `${event.clientY - 8}px`;
      els.tip.style.opacity = "1";
      renderer.domElement.style.cursor = "pointer";
    } else {
      if (state.selectedIndex < 0) state.hoveredIndex = -1;
      els.tip.style.opacity = "0";
      renderer.domElement.style.cursor = state.dragging ? "grabbing" : "grab";
    }
  }

  function bindEvents() {
    document.querySelectorAll(".ve").forEach(btn => btn.addEventListener("click", () => setWorld(btn.dataset.world)));
    document.querySelectorAll(".wb").forEach(btn => btn.addEventListener("click", () => setWorld(btn.dataset.world)));
    document.querySelectorAll(".vb").forEach(btn => btn.addEventListener("click", () => setView(btn.dataset.view)));
    document.querySelectorAll(".db").forEach(btn => {
      btn.addEventListener("click", () => {
        state.discourseMode = btn.dataset.mode;
        document.querySelectorAll(".db").forEach(x => x.classList.toggle("active", x === btn));
        if (state.selectedIndex >= 0) selectExhibit(state.selectedIndex);
      });
    });

    els.deselectHint.addEventListener("click", deselect);
    window.appSetWorld = setWorld;
    window.appSetView = setView;
    window.appSelectExhibit = selectExhibit;

    renderer.domElement.addEventListener("pointermove", updateHoverFromPointer);

    renderer.domElement.addEventListener("pointerdown", event => {
      state.dragging = true;
      state.dragMoved = false;
      state.dragStart = { x: event.clientX, y: event.clientY };
      renderer.domElement.setPointerCapture(event.pointerId);
    });

    renderer.domElement.addEventListener("pointermove", event => {
      if (!state.dragging) return;
      const dx = event.clientX - state.dragStart.x;
      const dy = event.clientY - state.dragStart.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) state.dragMoved = true;
      state.camTargetTheta = wrap360(state.camTargetTheta - dx * 0.004);
      state.camTargetPhi = clamp(state.camTargetPhi - dy * 0.004, 0.3, Math.PI - 0.3);
      state.dragStart = { x: event.clientX, y: event.clientY };
    });

    renderer.domElement.addEventListener("pointerup", event => {
      const wasDrag = state.dragMoved;
      state.dragging = false;
      try { renderer.domElement.releasePointerCapture(event.pointerId); } catch {}

      if (!state.currentWorld) return;
      if (!wasDrag && state.hoveredIndex >= 0) selectExhibit(state.hoveredIndex);
      else if (!wasDrag && state.selectedIndex >= 0) deselect();
    });

    renderer.domElement.addEventListener("wheel", event => {
      event.preventDefault();
      state.camTargetRadius = clamp(state.camTargetRadius + event.deltaY * 0.0035, 5.4, 12.5);
    }, { passive: false });

    document.addEventListener("keydown", event => {
      if (event.key === "Escape") deselect();
    });

    window.addEventListener("resize", () => {
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
      resizeConnector();
    });
  }

  function animate() {
    requestAnimationFrame(animate);
    const t = performance.now() * 0.001;

    if (!state.dragging) state.camTargetTheta = wrap360(state.camTargetTheta + 0.00045);
    state.camTheta += (state.camTargetTheta - state.camTheta) * 0.04;
    state.camPhi += (state.camTargetPhi - state.camPhi) * 0.04;
    state.camRadius += (state.camTargetRadius - state.camRadius) * 0.08;

    const r = state.camRadius;
    camera.position.set(
      r * Math.sin(state.camPhi) * Math.sin(state.camTheta),
      r * Math.cos(state.camPhi),
      r * Math.sin(state.camPhi) * Math.cos(state.camTheta)
    );
    camera.lookAt(0, 0, 0);

    if (stars) {
      stars.rotation.y = t * 0.01;
      stars.rotation.x = Math.sin(t * 0.08) * 0.03;
    }

    state.meshes.forEach((mesh, i) => {
      if (state.currentWorld) mesh.position.lerp(state.targets[i], 0.035);
      const selected = state.selectedIndex === i;
      const hovered = state.hoveredIndex === i;
      const hasSelection = state.selectedIndex >= 0;
      const similar = hasSelection && (state.exhibits[state.selectedIndex]?.similar?.[state.currentWorld]?.[state.currentView] || []).includes(i);
      const targetScale = selected ? 2.2 : hovered ? 1.55 : similar ? 1.25 : 1;
      mesh.scale.setScalar(mesh.scale.x + (targetScale - mesh.scale.x) * 0.12);
      const targetOpacity = !hasSelection ? 0.82 : selected ? 1 : similar ? 0.78 : 0.22;
      mesh.material.opacity += (targetOpacity - mesh.material.opacity) * 0.08;
      mesh.userData.halo.material.opacity += ((selected ? 0.16 : hovered ? 0.09 : 0.025) - mesh.userData.halo.material.opacity) * 0.08;
      mesh.userData.halo.material.color.copy(mesh.material.color);
    });

    updateLabelPositions();
    renderer.render(scene, camera);
  }

  async function init() {
    setupThree();

    // Important: bind immediately, before any fetch.
    bindEvents();

    // Demo points are available immediately, so the three world buttons always work.
    replaceData(makeDemoData());

    const params = new URLSearchParams(location.search);
    const requestedView = params.get("view");
    const requestedWorld = params.get("world");

    if (requestedView && VIEWS.includes(requestedView)) {
      state.currentView = requestedView;
      document.querySelectorAll(".vb").forEach(btn => btn.classList.toggle("active", btn.dataset.view === requestedView));
    }
    if (requestedWorld && WORLD_CONFIG[requestedWorld]) setWorld(requestedWorld);

    animate();

    try {
      const realData = await loadExpoData();
      replaceData(realData);
      const oldError = document.querySelector(".loading-error");
      if (oldError) oldError.remove();
    } catch (error) {
      showError(error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
