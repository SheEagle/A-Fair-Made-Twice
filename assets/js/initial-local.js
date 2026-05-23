(function () {
  const THREE = window.THREE;
  const EXHIBITS = Array.isArray(window.REAL_EXHIBITS) ? window.REAL_EXHIBITS : [];

  if (!THREE) throw new Error("Three.js failed to load.");

  const VIEW_TO_KEY = {
    overall: "overall",
    technical: "made",
    category: "is",
    exhibition: "belongs",
    perception: "seen"
  };

  // ─── 世界配置：宇宙收紧，三个世界清晰可辨但不至于太空 ───────────────────
  const WORLD_CONFIG = {
    official: {
      label: "The Official World",
      className: "official",
      color: new THREE.Color(0xa8c4ff),
      orbit: -0.12,
      scale: [2.2, 1.8, 2.0],
      offset: [0.0, 0.0, 0.0],
      pointTint: 0.14,
      bubbleW: 220,
      cardW: 220
    },
    staged: {
      label: "The Staged World",
      className: "staged",
      color: new THREE.Color(0xe2b87a),
      orbit: 0.76,
      scale: [2.4, 1.6, 2.2],
      offset: [5.2, 0.4, -2.1],
      pointTint: 0.22,
      bubbleW: 220,
      cardW: 220
    },
    lived: {
      label: "The Lived World",
      className: "lived",
      color: new THREE.Color(0xffaabf),
      orbit: -0.78,
      scale: [2.2, 2.0, 1.9],
      offset: [-5.1, -0.3, 1.9],
      pointTint: 0.18,
      bubbleW: 220,
      cardW: 220
    },
    unfinished: {
      label: "The Unfinished World",
      className: "unfinished",
      color: new THREE.Color(0xc4a882),
      orbit: 0.38,
      scale: [2.0, 2.6, 1.7],
      offset: [-2.4, 2.8, -4.6],
      pointTint: 0.16,
      bubbleW: 220,
      cardW: 220
    }
  };

  const els = {
    host:         document.getElementById("renderer-host"),
    pointLayer:   document.getElementById("point-layer"),
    labels:       document.getElementById("label-root"),
    intro:        document.getElementById("intro"),
    worldBar:     document.getElementById("world-bar"),
    viewBar:      document.getElementById("view-bar"),
    deselectHint: document.getElementById("deselect-hint"),
    tip:          document.getElementById("tip"),
    tipName:      document.getElementById("tip-name"),
    tipThumbWrap: document.getElementById("tip-thumb-wrap"),
    tipThumb:     document.getElementById("tip-thumb"),
    connector:    document.getElementById("connector-canvas"),
    imagePanel:        document.getElementById("image-panel"),
    bubbleLayer:       document.getElementById("bubble-layer"),
    imagePanelImg:     document.getElementById("image-panel-img"),
    imagePanelTitle:   document.getElementById("image-panel-title"),
    imagePanelCaption: document.getElementById("image-panel-caption"),
    imagePanelEssay:   document.getElementById("image-panel-essay"),
    modeToggle:        document.getElementById("mode-toggle"),
    worldGhost:        document.getElementById("world-ghost")
  };

  const ctx = els.connector.getContext("2d");

  const state = {
    currentWorld:    null,
    currentView:     "overall",
    selectedIndex:   -1,
    hoveredIndex:    -1,
    pointMode:       "dots",
    meshes:          [],
    targets:         [],
    pointEls:        [],
    nameLabelEls:    [],
    labels:          [],
    dragging:        false,
    dragMoved:       false,
    dragStart:       { x: 0, y: 0 },
    camTheta:        0,
    camPhi:          Math.PI * 0.44,
    camTargetTheta:  0,
    camTargetPhi:    Math.PI * 0.44,
    camRadius:       13.5,
    camTargetRadius: 13.5,
    camFov:          60,
    camTargetFov:    60
  };

  // ─── 工具函数 ──────────────────────────────────────────────────────────────
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  function wrap360(v) {
    const TWO_PI = Math.PI * 2;
    while (v < 0) v += TWO_PI;
    while (v >= TWO_PI) v -= TWO_PI;
    return v;
  }

  function escapeHtml(v) {
    return String(v ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  function colorToCss(c, a = 1) {
    return `rgba(${Math.round(c.r*255)},${Math.round(c.g*255)},${Math.round(c.b*255)},${a})`;
  }

  function project(vec, cam) {
    const p = vec.clone().project(cam);
    return {
      x: (p.x * 0.5 + 0.5) * innerWidth,
      y: (-0.5 * p.y + 0.5) * innerHeight,
      z: p.z
    };
  }

  function resizeConnector() {
    els.connector.width = innerWidth;
    els.connector.height = innerHeight;
  }

  function showFatal(msg) {
    const box = document.createElement("div");
    box.className = "loading-error";
    box.innerHTML = `<strong>Interactive demo failed.</strong><br>${escapeHtml(msg)}`;
    document.body.appendChild(box);
  }

  if (!EXHIBITS.length) { showFatal("No exhibit data in initial.data.js."); return; }

  resizeConnector();

  // ─── Three.js 场景 ─────────────────────────────────────────────────────────
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setSize(innerWidth, innerHeight);
  renderer.setClearColor(0x04040e, 0);
  els.host.appendChild(renderer.domElement);

  const scene  = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.1, 200);
  camera.position.set(0, 0, 13.5);

  const bridgeGroup = new THREE.Group();
  scene.add(bridgeGroup);

  // ─── 星空：适配收紧后的宇宙 ───────────────────────────────────────────────
  function makeStars() {
    const count = 2200;
    const geo   = new THREE.BufferGeometry();
    const pos   = new Float32Array(count * 3);
    const col   = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
      const r = 12 + Math.random() * 48;
      const a = Math.random() * Math.PI * 2;
      const b = Math.acos(2 * Math.random() - 1);
      pos[i*3]   = r * Math.sin(b) * Math.cos(a);
      pos[i*3+1] = r * Math.sin(b) * Math.sin(a) * 0.72;
      pos[i*3+2] = r * Math.cos(b);

      const v = 0.52 + Math.random() * 0.48;
      col[i*3]   = v;
      col[i*3+1] = v * (0.85 + Math.random() * 0.15);
      col[i*3+2] = v * (0.80 + Math.random() * 0.20);
    }

    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color",    new THREE.BufferAttribute(col, 3));

    const stars = new THREE.Points(geo, new THREE.PointsMaterial({
      size: 0.055,
      vertexColors: true,
      transparent: true,
      opacity: 0.82,
      blending: THREE.AdditiveBlending,
      depthWrite: false
    }));
    scene.add(stars);
    return stars;
  }

  const stars = makeStars();

  // ─── 位置变换：带抗重叠微抖 ───────────────────────────────────────────────
  function orbitTransform(world, p, i) {
    const cfg = WORLD_CONFIG[world];
    const c = Math.cos(cfg.orbit), s = Math.sin(cfg.orbit);

    let x = (p?.[0] ?? 0) * cfg.scale[0];
    let y = (p?.[1] ?? 0) * cfg.scale[1];
    let z = (p?.[2] ?? 0) * cfg.scale[2];

    // 黄金角抖动，均匀分布，不重叠
    const jx = Math.sin(i * 2.399) * 0.38;
    const jy = Math.cos(i * 1.618) * 0.30;
    const jz = Math.sin(i * 3.141) * 0.38;

    x += jx + (world === "lived"       ? Math.cos(i * 1.7)  * 0.10 : 0);
    y += jy + (world === "staged"      ? Math.sin(i * 1.13) * 0.10 : 0)
            + (world === "unfinished"  ? Math.cos(i * 2.29) * 0.12 : 0);
    z += jz + (world === "official"   ? Math.sin(i * 0.58) * 0.10 : 0)
            + (world === "unfinished"  ? Math.sin(i * 1.41) * 0.12 : 0);

    const rotatedX = x * c - z * s;
    const rotatedZ = x * s + z * c;
    const len = Math.max(Math.hypot(rotatedX, y, rotatedZ), 1e-6);
    const semanticRadius = clamp(len, 0.0, 5.6);
    const shellRadius = 8.4 + semanticRadius * 1.45 + (i % 9) * 0.08;

    return [
      (rotatedX / len) * shellRadius,
      (y / len) * shellRadius,
      (rotatedZ / len) * shellRadius
    ];
  }

  function activeColor() {
    return WORLD_CONFIG[state.currentWorld]?.color || new THREE.Color(0xffffff);
  }

  function currentViewKey() {
    return VIEW_TO_KEY[state.currentView] || "overall";
  }

  function getBasePosition(exhibit, world, viewKey) {
    return exhibit.pos?.[world]?.[viewKey]
      || exhibit.pos?.[world]?.overall
      || exhibit.pos?.official?.overall
      || [0, 0, 0];
  }

  function getNarratives(exhibit, world, viewKey) {
    // Unfinished world: gather one representative narrative from each of the three worlds
    if (world === "unfinished") {
      const cross = [];
      ["official", "staged", "lived"].forEach(w => {
        const s = exhibit.narratives?.[w] || {};
        const pool = s.overall?.length ? s.overall
                   : ["made","is","belongs","seen"].map(k => s[k]?.[0]).filter(Boolean);
        if (pool[0]) cross.push(pool[0]);
      });
      return cross;
    }
    const scoped = exhibit.narratives?.[world] || {};
    if (viewKey === "overall") {
      if (scoped.overall?.length) return scoped.overall;
      const g = [];
      ["made","is","belongs","seen"].forEach(k => {
        if (scoped[k]?.length) g.push(...scoped[k].slice(0,1));
      });
      return g;
    }
    return scoped[viewKey] || [];
  }

  function getDensity(exhibit, world, viewKey) {
    const w = world === "unfinished" ? "official" : world;
    const n = getNarratives(exhibit, w, viewKey).length
           || getNarratives(exhibit, w, "overall").length;
    return clamp(n / 9, 0.22, 1);
  }

  function getSimilarIds(exhibit) {
    const vk  = currentViewKey();
    const w   = state.currentWorld === "unfinished" ? "official" : state.currentWorld;
    return exhibit.similar?.[w]?.[vk]
      || exhibit.similar?.[w]?.overall
      || [];
  }

  function getSimilarReason(exhibit, ti) {
    const vk = currentViewKey();
    const w  = state.currentWorld === "unfinished" ? "official" : state.currentWorld;
    return exhibit.simReason?.[w]?.[vk]?.[String(ti)]
      || exhibit.simReason?.[w]?.overall?.[String(ti)]
      || `${WORLD_CONFIG[state.currentWorld].label} · ${state.currentView}`;
  }

  // ─── 网格 & 点位层 ─────────────────────────────────────────────────────────
  function getArchiveId(exhibit) {
    const raw = exhibit?.archiveId ?? exhibit?.rawMetadata?.archive_id ?? "";
    return String(raw).trim();
  }

  function getRestoredImagePath(exhibit) {
    const archiveId = getArchiveId(exhibit);
    if (!archiveId) return null;
    return `./Restored/${archiveId.padStart(4, "0")}_c_l.png`;
  }

  /* ── 气泡粒子 ──────────────────────────────────────────────────────────── */
  let _bubbleTimer = null;

  function _spawnBubble() {
    if (!els.imagePanel || !els.imagePanel.classList.contains("on")) return;
    if (!els.bubbleLayer) return;
    const r   = els.imagePanel.getBoundingClientRect();
    const bub = document.createElement("div");
    bub.className = "panel-bubble";

    // Pick a random point on the panel perimeter
    const perim = 2 * (r.width + r.height);
    const pos   = Math.random() * perim;
    let bx, by;
    if      (pos < r.width)                        { bx = r.left + pos;                          by = r.top;    }
    else if (pos < r.width + r.height)             { bx = r.right;                               by = r.top  + (pos - r.width); }
    else if (pos < 2 * r.width + r.height)         { bx = r.right - (pos - r.width - r.height); by = r.bottom; }
    else                                           { bx = r.left;  by = r.bottom - (pos - 2 * r.width - r.height); }

    const size  = 3 + Math.random() * 7;
    const dur   = 3 + Math.random() * 3.5;
    // drift outward from panel centre with a gentle upward bias
    const cx    = r.left + r.width  / 2;
    const cy    = r.top  + r.height / 2;
    const ang   = Math.atan2(by - cy, bx - cx);
    const dist  = 32 + Math.random() * 48;
    const dx    = Math.cos(ang) * dist;
    const dy    = Math.sin(ang) * dist - 8;

    bub.style.cssText = `left:${(bx - size / 2).toFixed(1)}px;top:${(by - size / 2).toFixed(1)}px;width:${size.toFixed(1)}px;height:${size.toFixed(1)}px;--dx:${dx.toFixed(1)}px;--dy:${dy.toFixed(1)}px;--dur:${dur.toFixed(2)}s;`;
    els.bubbleLayer.appendChild(bub);
    setTimeout(() => { if (bub.parentNode) bub.parentNode.removeChild(bub); }, dur * 1000 + 120);
  }

  function startBubbles() {
    stopBubbles();
    _spawnBubble();
    _bubbleTimer = setInterval(_spawnBubble, 480);
  }

  function stopBubbles() {
    if (_bubbleTimer) { clearInterval(_bubbleTimer); _bubbleTimer = null; }
    if (els.bubbleLayer) els.bubbleLayer.innerHTML = "";
  }

  function hideImagePanel() {
    if (!els.imagePanel) return;
    stopBubbles();
    els.imagePanel.classList.remove("on");
    els.imagePanel.setAttribute("aria-hidden", "true");

    if (els.imagePanelImg) {
      els.imagePanelImg.removeAttribute("src");
      els.imagePanelImg.alt = "Selected exhibit image";
      els.imagePanelImg.onerror = null;
      els.imagePanelImg.onload = null;
    }
    if (els.imagePanelTitle)   els.imagePanelTitle.textContent   = "";
    if (els.imagePanelCaption) els.imagePanelCaption.textContent = "";
    if (els.imagePanelEssay)   els.imagePanelEssay.textContent   = "";
  }

  function updateImagePanel(exhibit, world, vk) {
    if (!els.imagePanel || !els.imagePanelImg || !els.imagePanelCaption) return;

    const archiveId = getArchiveId(exhibit);
    const src = getRestoredImagePath(exhibit);
    if (!archiveId || !src) {
      hideImagePanel();
      return;
    }

    // 展品名称
    if (els.imagePanelTitle) els.imagePanelTitle.textContent = exhibit.name;

    // 档案标注（微型 mono）
    els.imagePanelCaption.textContent =
      `archive ${archiveId.padStart(4, "0")}  ·  ${(exhibit.country || exhibit.location || "").toUpperCase()}`;

    // 策展文字（非 unfinished world）或留空由 unfinished-world.js 注入
    if (els.imagePanelEssay) {
      const w = world || state.currentWorld || "official";
      if (w === "unfinished") {
        els.imagePanelEssay.innerHTML = "";   // unfinished-world.js fills this
      } else {
        const k = vk || currentViewKey() || "overall";
        const narrs = getNarratives(exhibit, w, k);
        const essayParts = narrs.slice(0, 3).map(n => n.val || n.value || "").filter(Boolean);
        els.imagePanelEssay.textContent = essayParts.join("  ·  ");
      }
    }

    els.imagePanelImg.alt = `${exhibit.name} stereo view`;
    els.imagePanelImg.onerror = () => hideImagePanel();
    els.imagePanelImg.onload = () => {
      els.imagePanel.classList.add("on");
      els.imagePanel.setAttribute("aria-hidden", "false");
      startBubbles();
    };
    els.imagePanelImg.src = src;
  }

  function makeMeshes() {
    EXHIBITS.forEach((ex, i) => {
      const baseColor = new THREE.Color(ex.color || "#ffffff");
      // 极小的隐形球体，仅用于位置插值和投影计算
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(0.001, 4, 4),
        new THREE.MeshBasicMaterial({ color: baseColor, transparent: true, opacity: 0 })
      );
      mesh.position.set(
        (Math.random()-0.5)*10,
        (Math.random()-0.5)*7,
        (Math.random()-0.5)*10
      );
      mesh.userData = { index: i, baseColor };

      // 保留 halo 结构以防其他地方引用
      const halo = new THREE.Mesh(
        new THREE.SphereGeometry(0.001, 4, 4),
        new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false })
      );
      mesh.add(halo);
      mesh.userData.halo = halo;
      state.meshes.push(mesh);
      state.targets.push(mesh.position.clone());
      scene.add(mesh);
    });
  }

  // ─── 形状生成器：基于世界类型和展品索引 ────────────────────────────────────
  //
  //  三种世界 × 四种密度级别 = 丰富形态
  //  official → 菱形/正方形（档案、方正、制度）
  //  staged   → 六边形/圆形（剧场、舞台、完满）
  //  lived    → 不规则星形/泪珠（感知、身体、流动）

  function getShapeType(world, exhibitIndex, density) {
    const tier = density < 0.35 ? 0 : density < 0.60 ? 1 : density < 0.82 ? 2 : 3;
    // 每个展品有固定的形态偏好（基于索引）
    const bias = exhibitIndex % 3; // 0/1/2
    if (world === "official") return ["diamond", "square", "cross", "compass"][tier];
    if (world === "staged")   return ["hexagon", "circle", "double-ring", "star6"][tier];
    if (world === "lived")    return ["teardrop", "oval", "star5", "cluster"][tier];
    return "circle";
  }

  // 生成 SVG path/shape 字符串
  function buildPointSVG(world, index, density, colorHex) {
    const shape = getShapeType(world, index, density);
    const tier  = density < 0.35 ? 0 : density < 0.60 ? 1 : density < 0.82 ? 2 : 3;

    // 基础尺寸随密度增大
    const baseR = 4 + density * 5; // 4–9px

    // 颜色
    const fill   = colorHex;
    const stroke = colorHex;

    // 脉冲环（3层，用于选中态动画）
    const pulseRings = `
      <circle class="ep-pulse" cx="0" cy="0" r="${baseR * 1.2}" fill="none" stroke="${stroke}" stroke-width="1" opacity="0"/>
      <circle class="ep-pulse" cx="0" cy="0" r="${baseR * 1.2}" fill="none" stroke="${stroke}" stroke-width="0.8" opacity="0"/>
      <circle class="ep-pulse" cx="0" cy="0" r="${baseR * 1.2}" fill="none" stroke="${stroke}" stroke-width="0.6" opacity="0"/>
    `;

    // 相似点虚线环
    const simRing = `<circle class="ep-similar-ring" cx="0" cy="0" r="${baseR * 2.2}"
      fill="none" stroke="${stroke}" stroke-width="1" opacity="0"/>`;

    // 呼吸光晕
    const halo = `<circle class="ep-halo" cx="0" cy="0" r="${baseR * 2.6}"
      fill="${fill}" opacity="0.10"/>`;

    let coreShape = "";
    let outerRing = "";
    let crosshair = "";

    // ── 菱形（official，低密度）──
    if (shape === "diamond") {
      const s = baseR;
      coreShape = `<polygon class="ep-core ep-shape" points="0,${-s} ${s},0 0,${s} ${-s},0"
        fill="${fill}" opacity="0.90"/>`;
      outerRing = `<polygon class="ep-ring" points="0,${-(s*2.0)} ${s*2.0},0 0,${s*2.0} ${-(s*2.0)},0"
        fill="none" stroke="${stroke}" stroke-width="0.8" opacity="0"/>`;
      crosshair = `
        <line class="ep-crosshair" x1="0" y1="${-(s*2.5)}" x2="0" y2="${s*2.5}" stroke="${stroke}" stroke-width="0.7" opacity="0"/>
        <line class="ep-crosshair" x1="${-(s*2.5)}" y1="0" x2="${s*2.5}" y2="0" stroke="${stroke}" stroke-width="0.7" opacity="0"/>
        <polygon class="ep-crosshair" points="0,${-(s*1.2)} ${s*1.2},0 0,${s*1.2} ${-(s*1.2)},0"
          fill="none" stroke="${stroke}" stroke-width="0.9" opacity="0"/>`;
    }

    // ── 正方形（official，中密度）──
    else if (shape === "square") {
      const s = baseR * 0.82;
      coreShape = `<rect class="ep-core ep-shape" x="${-s}" y="${-s}" width="${s*2}" height="${s*2}"
        fill="${fill}" opacity="0.88" rx="1"/>`;
      outerRing = `<rect class="ep-ring" x="${-s*1.9}" y="${-s*1.9}" width="${s*3.8}" height="${s*3.8}"
        fill="none" stroke="${stroke}" stroke-width="0.8" opacity="0" rx="2"/>`;
      crosshair = `
        <line class="ep-crosshair" x1="0" y1="${-(s*2.4)}" x2="0" y2="${s*2.4}" stroke="${stroke}" stroke-width="0.7" opacity="0"/>
        <line class="ep-crosshair" x1="${-(s*2.4)}" y1="0" x2="${s*2.4}" y2="0" stroke="${stroke}" stroke-width="0.7" opacity="0"/>`;
    }

    // ── 十字（official，高密度）──
    else if (shape === "cross") {
      const s = baseR, t = s * 0.38;
      coreShape = `<path class="ep-core ep-shape" d="
        M${-t},${-s} L${t},${-s} L${t},${-t} L${s},${-t} L${s},${t}
        L${t},${t} L${t},${s} L${-t},${s} L${-t},${t} L${-s},${t}
        L${-s},${-t} L${-t},${-t} Z"
        fill="${fill}" opacity="0.86"/>`;
      outerRing = `<circle class="ep-ring" cx="0" cy="0" r="${s*1.9}"
        fill="none" stroke="${stroke}" stroke-width="0.8" opacity="0"/>`;
      crosshair = `
        <line class="ep-crosshair" x1="0" y1="${-(s*2.4)}" x2="0" y2="${s*2.4}" stroke="${stroke}" stroke-width="0.7" opacity="0"/>
        <line class="ep-crosshair" x1="${-(s*2.4)}" y1="0" x2="${s*2.4}" y2="0" stroke="${stroke}" stroke-width="0.7" opacity="0"/>`;
    }

    // ── 指南针（official，顶级密度）──
    else if (shape === "compass") {
      const s = baseR;
      coreShape = `
        <polygon class="ep-core ep-shape" points="0,${-s} ${s*0.38},0 0,${s*0.55} ${-s*0.38},0"
          fill="${fill}" opacity="0.94"/>
        <circle cx="0" cy="0" r="${s*0.22}" fill="${fill}" opacity="0.60"/>`;
      outerRing = `
        <circle class="ep-ring" cx="0" cy="0" r="${s*1.8}" fill="none" stroke="${stroke}" stroke-width="0.7" opacity="0"/>
        <circle class="ep-ring" cx="0" cy="0" r="${s*2.4}" fill="none" stroke="${stroke}" stroke-width="0.4" stroke-dasharray="2 4" opacity="0"/>`;
      crosshair = `
        <line class="ep-crosshair" x1="0" y1="${-(s*2.6)}" x2="0" y2="${s*2.6}" stroke="${stroke}" stroke-width="0.6" opacity="0" stroke-dasharray="2 3"/>
        <line class="ep-crosshair" x1="${-(s*2.6)}" y1="0" x2="${s*2.6}" y2="0" stroke="${stroke}" stroke-width="0.6" opacity="0" stroke-dasharray="2 3"/>
        <polygon class="ep-crosshair" points="0,${-s*1.4} ${s*1.4},0 0,${s*1.4} ${-s*1.4},0"
          fill="none" stroke="${stroke}" stroke-width="0.9" opacity="0"/>`;
    }

    // ── 六边形（staged，低密度）──
    else if (shape === "hexagon") {
      const pts = Array.from({length:6}, (_,k) => {
        const a = k * Math.PI/3 - Math.PI/6;
        return `${baseR*Math.cos(a)},${baseR*Math.sin(a)}`;
      }).join(" ");
      const pts2 = Array.from({length:6}, (_,k) => {
        const a = k * Math.PI/3 - Math.PI/6;
        return `${baseR*1.9*Math.cos(a)},${baseR*1.9*Math.sin(a)}`;
      }).join(" ");
      coreShape = `<polygon class="ep-core ep-shape" points="${pts}" fill="${fill}" opacity="0.88"/>`;
      outerRing = `<polygon class="ep-ring" points="${pts2}" fill="none" stroke="${stroke}" stroke-width="0.8" opacity="0"/>`;
      crosshair = `
        <polygon class="ep-crosshair" points="${pts2}" fill="none" stroke="${stroke}" stroke-width="0.9" opacity="0"/>
        <line class="ep-crosshair" x1="0" y1="${-(baseR*2.4)}" x2="0" y2="${baseR*2.4}" stroke="${stroke}" stroke-width="0.6" opacity="0"/>`;
    }

    // ── 圆形（staged，中密度）──
    else if (shape === "circle") {
      coreShape = `<circle class="ep-core ep-shape" cx="0" cy="0" r="${baseR}" fill="${fill}" opacity="0.88"/>`;
      outerRing = `<circle class="ep-ring" cx="0" cy="0" r="${baseR*1.85}" fill="none" stroke="${stroke}" stroke-width="0.8" opacity="0"/>`;
      crosshair = `
        <circle class="ep-crosshair" cx="0" cy="0" r="${baseR*1.3}" fill="none" stroke="${stroke}" stroke-width="0.9" opacity="0"/>
        <line class="ep-crosshair" x1="0" y1="${-(baseR*2.2)}" x2="0" y2="${baseR*2.2}" stroke="${stroke}" stroke-width="0.6" opacity="0"/>
        <line class="ep-crosshair" x1="${-(baseR*2.2)}" y1="0" x2="${baseR*2.2}" y2="0" stroke="${stroke}" stroke-width="0.6" opacity="0"/>`;
    }

    // ── 双环（staged，高密度）──
    else if (shape === "double-ring") {
      coreShape = `
        <circle class="ep-core ep-shape" cx="0" cy="0" r="${baseR*0.52}" fill="${fill}" opacity="0.96"/>
        <circle cx="0" cy="0" r="${baseR}" fill="none" stroke="${fill}" stroke-width="1.2" opacity="0.60"/>`;
      outerRing = `<circle class="ep-ring" cx="0" cy="0" r="${baseR*1.9}" fill="none" stroke="${stroke}" stroke-width="0.8" opacity="0"/>`;
      crosshair = `
        <circle class="ep-crosshair" cx="0" cy="0" r="${baseR*1.3}" fill="none" stroke="${stroke}" stroke-width="0.9" opacity="0"/>
        <line class="ep-crosshair" x1="0" y1="${-(baseR*2.4)}" x2="0" y2="${baseR*2.4}" stroke="${stroke}" stroke-width="0.6" opacity="0"/>
        <line class="ep-crosshair" x1="${-(baseR*2.4)}" y1="0" x2="${baseR*2.4}" y2="0" stroke="${stroke}" stroke-width="0.6" opacity="0"/>`;
    }

    // ── 六角星（staged，顶级密度）──
    else if (shape === "star6") {
      const starPts = Array.from({length:12}, (_,k) => {
        const r = k%2===0 ? baseR : baseR*0.46;
        const a = k * Math.PI/6 - Math.PI/2;
        return `${r*Math.cos(a)},${r*Math.sin(a)}`;
      }).join(" ");
      coreShape = `<polygon class="ep-core ep-shape" points="${starPts}" fill="${fill}" opacity="0.90"/>`;
      outerRing = `<circle class="ep-ring" cx="0" cy="0" r="${baseR*2.0}" fill="none" stroke="${stroke}" stroke-width="0.7" opacity="0"/>`;
      crosshair = `
        <circle class="ep-crosshair" cx="0" cy="0" r="${baseR*1.35}" fill="none" stroke="${stroke}" stroke-width="0.9" opacity="0"/>
        <line class="ep-crosshair" x1="0" y1="${-(baseR*2.4)}" x2="0" y2="${baseR*2.4}" stroke="${stroke}" stroke-width="0.6" opacity="0"/>
        <line class="ep-crosshair" x1="${-(baseR*2.4)}" y1="0" x2="${baseR*2.4}" y2="0" stroke="${stroke}" stroke-width="0.6" opacity="0"/>`;
    }

    // ── 泪珠（lived，低密度）──
    else if (shape === "teardrop") {
      const s = baseR;
      coreShape = `<path class="ep-core ep-shape" d="
        M0,${-s*1.1}
        C${s*0.8},${-s*0.4} ${s*0.9},${s*0.5} 0,${s*0.9}
        C${-s*0.9},${s*0.5} ${-s*0.8},${-s*0.4} 0,${-s*1.1} Z"
        fill="${fill}" opacity="0.88"/>`;
      outerRing = `<ellipse class="ep-ring" cx="0" cy="0" rx="${s*1.8}" ry="${s*2.1}"
        fill="none" stroke="${stroke}" stroke-width="0.8" opacity="0"/>`;
      crosshair = `
        <ellipse class="ep-crosshair" cx="0" cy="0" rx="${s*1.2}" ry="${s*1.4}"
          fill="none" stroke="${stroke}" stroke-width="0.9" opacity="0"/>
        <line class="ep-crosshair" x1="0" y1="${-(s*2.4)}" x2="0" y2="${s*2.4}" stroke="${stroke}" stroke-width="0.6" opacity="0"/>`;
    }

    // ── 椭圆（lived，中密度）──
    else if (shape === "oval") {
      const rx = baseR * 1.3, ry = baseR * 0.76;
      coreShape = `<ellipse class="ep-core ep-shape" cx="0" cy="0" rx="${rx}" ry="${ry}"
        fill="${fill}" opacity="0.88"/>`;
      outerRing = `<ellipse class="ep-ring" cx="0" cy="0" rx="${rx*1.85}" ry="${ry*1.85}"
        fill="none" stroke="${stroke}" stroke-width="0.8" opacity="0"/>`;
      crosshair = `
        <ellipse class="ep-crosshair" cx="0" cy="0" rx="${rx*1.2}" ry="${ry*1.2}"
          fill="none" stroke="${stroke}" stroke-width="0.9" opacity="0"/>
        <line class="ep-crosshair" x1="${-(rx*2.2)}" y1="0" x2="${rx*2.2}" y2="0" stroke="${stroke}" stroke-width="0.6" opacity="0"/>`;
    }

    // ── 五角星（lived，高密度）──
    else if (shape === "star5") {
      const starPts = Array.from({length:10}, (_,k) => {
        const r = k%2===0 ? baseR : baseR*0.42;
        const a = k * Math.PI/5 - Math.PI/2;
        return `${r*Math.cos(a)},${r*Math.sin(a)}`;
      }).join(" ");
      coreShape = `<polygon class="ep-core ep-shape" points="${starPts}" fill="${fill}" opacity="0.90"/>`;
      outerRing = `<circle class="ep-ring" cx="0" cy="0" r="${baseR*2.0}" fill="none" stroke="${stroke}" stroke-width="0.7" opacity="0"/>`;
      crosshair = `
        <circle class="ep-crosshair" cx="0" cy="0" r="${baseR*1.4}" fill="none" stroke="${stroke}" stroke-width="0.9" opacity="0"/>
        <line class="ep-crosshair" x1="0" y1="${-(baseR*2.4)}" x2="0" y2="${baseR*2.4}" stroke="${stroke}" stroke-width="0.6" opacity="0"/>
        <line class="ep-crosshair" x1="${-(baseR*2.4)}" y1="0" x2="${baseR*2.4}" y2="0" stroke="${stroke}" stroke-width="0.6" opacity="0"/>`;
    }

    // ── 簇（lived，顶级密度）——多个小圆聚合 ──
    else if (shape === "cluster") {
      const s = baseR * 0.55;
      const offsets = [[0,-baseR*0.9],[baseR*0.78,baseR*0.48],[-baseR*0.78,baseR*0.48]];
      coreShape = offsets.map(([ox,oy]) =>
        `<circle class="ep-core ep-shape" cx="${ox}" cy="${oy}" r="${s}" fill="${fill}" opacity="0.86"/>`
      ).join("");
      outerRing = `<circle class="ep-ring" cx="0" cy="0" r="${baseR*2.0}" fill="none" stroke="${stroke}" stroke-width="0.7" opacity="0"/>`;
      crosshair = `
        <circle class="ep-crosshair" cx="0" cy="0" r="${baseR*1.5}" fill="none" stroke="${stroke}" stroke-width="0.9" opacity="0"/>
        <line class="ep-crosshair" x1="0" y1="${-(baseR*2.4)}" x2="0" y2="${baseR*2.4}" stroke="${stroke}" stroke-width="0.6" opacity="0"/>
        <line class="ep-crosshair" x1="${-(baseR*2.4)}" y1="0" x2="${baseR*2.4}" y2="0" stroke="${stroke}" stroke-width="0.6" opacity="0"/>`;
    }

    // 默认回退
    else {
      coreShape = `<circle class="ep-core ep-shape" cx="0" cy="0" r="${baseR}" fill="${fill}" opacity="0.88"/>`;
      outerRing = `<circle class="ep-ring" cx="0" cy="0" r="${baseR*1.85}" fill="none" stroke="${stroke}" stroke-width="0.8" opacity="0"/>`;
      crosshair = `<circle class="ep-crosshair" cx="0" cy="0" r="${baseR*1.3}" fill="none" stroke="${stroke}" stroke-width="0.9" opacity="0"/>`;
    }

    const size = (baseR * 3.2 + 20) * 2;
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="${-size/2} ${-size/2} ${size} ${size}">
      <defs>
        <filter id="glow-${index}">
          <feGaussianBlur stdDeviation="1.8" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      ${halo}
      ${outerRing}
      ${simRing}
      <g filter="url(#glow-${index})">
        ${coreShape}
      </g>
      ${crosshair}
      ${pulseRings}
    </svg>`;
  }

  // 缓存当前世界的颜色（hex）
  function colorToHex(c) {
    const r = Math.round(c.r*255).toString(16).padStart(2,"0");
    const g = Math.round(c.g*255).toString(16).padStart(2,"0");
    const b = Math.round(c.b*255).toString(16).padStart(2,"0");
    return `#${r}${g}${b}`;
  }

  function makePointLayer() {
    EXHIBITS.forEach((ex, i) => {
      const pt = document.createElement("button");
      pt.type = "button";
      pt.className = "exhibit-point hidden";
      pt.setAttribute("aria-label", ex.name);
      // SVG 将在 applyLayout 后首次 updatePointLayer 时注入；图像覆盖在 SVG 之上
      pt.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="-22 -22 44 44"></svg>`;
      const thumb = document.createElement("img");
      thumb.className = "point-thumb";
      thumb.alt = ex.name;
      pt.appendChild(thumb);

      pt.addEventListener("mouseenter", () => {
        if (!state.currentWorld) return;
        state.hoveredIndex = i;
        document.body.style.cursor = "pointer";
      });
      pt.addEventListener("mouseleave", () => {
        if (state.selectedIndex !== i) state.hoveredIndex = -1;
        els.tip.style.opacity = "0";
        document.body.style.cursor = "default";
      });
      pt.addEventListener("mousemove", ev => {
        if (!state.currentWorld) return;
        state.hoveredIndex = i;
        els.tipName.textContent = EXHIBITS[i].name;
        els.tip.style.left  = `${ev.clientX + 16}px`;
        els.tip.style.top   = `${ev.clientY - 8}px`;
        els.tip.style.opacity = "1";
        // Load thumbnail once per exhibit
        if (els.tipThumb && els.tipThumbWrap) {
          const src = getRestoredImagePath(EXHIBITS[i]);
          if (src && els.tipThumb.dataset.src !== src) {
            els.tipThumb.dataset.src = src;
            els.tipThumb.classList.remove("loaded");
            els.tipThumbWrap.style.display = "";
            els.tipThumb.onerror = () => { els.tipThumbWrap.style.display = "none"; };
            els.tipThumb.onload  = () => { els.tipThumb.classList.add("loaded"); };
            els.tipThumb.src = src;
          }
        }
      });
      pt.addEventListener("click", ev => {
        ev.preventDefault(); ev.stopPropagation();
        if (!state.currentWorld) return;
        selectExhibit(i);
      });

      els.pointLayer.appendChild(pt);
      state.pointEls.push(pt);
    });
  }

  // 当世界或视角变化时，重新注入 SVG（形态会变）——保留 .point-thumb
  function rebuildPointSVGs() {
    if (!state.currentWorld) return;
    EXHIBITS.forEach((ex, i) => {
      const pt      = state.pointEls[i];
      const mesh    = state.meshes[i];
      const density = mesh.userData.density ?? getDensity(ex, state.currentWorld, currentViewKey());
      const color   = colorToHex(mesh.material.color);
      const thumb   = pt.querySelector(".point-thumb"); // 保存缩略图
      pt.innerHTML  = buildPointSVG(state.currentWorld, i, density, color);
      if (thumb) pt.appendChild(thumb);                // 还原缩略图
      pt.dataset.density = density < 0.35 ? "0" : density < 0.60 ? "1" : density < 0.82 ? "2" : "3";
    });
  }

  // ─── 标签管理 ──────────────────────────────────────────────────────────────
  function clearLabels() {
    state.labels.forEach(el => el.remove());
    state.labels = [];
    ctx.clearRect(0, 0, innerWidth, innerHeight);
  }

  // ─── 核心：精确无重叠布局 ─────────────────────────────────────────────────
  //
  //  详情布局：
  //  - 中央固定为展品图像
  //  - similar exhibit 独占右侧专栏
  //  - 信息泡泡围绕中央图像，但避开右侧专栏
  //  这样保留“围绕展品”的感觉，同时避免泡泡和 similar 卡片互相压住。

  const BUBBLE_W    = 238;
  const BUBBLE_H    = 82;    // 注释标签高度（含更多内边距）
  const BUBBLE_GAP  = 22;
  const CARD_W      = 234;
  const CARD_H      = 92;
  const CARD_GAP    = 28;

  function detailLayoutMetrics() {
    const centerX = innerWidth / 2;
    const centerY = innerHeight / 2;
    const imageW = clamp(innerWidth * 0.32, 380, 560);
    const imageH = clamp(innerHeight * 0.50, 330, 520);
    const simX = clamp(
      innerWidth - CARD_W / 2 - 84,
      centerX + imageW / 2 + CARD_W / 2 + 150,
      innerWidth - CARD_W / 2 - 42
    );
    const simLeft = simX - CARD_W / 2;
    return { centerX, centerY, imageW, imageH, simX, simLeft };
  }

  function applyElementCenter(el, cx, cy, w, h) {
    // 上方留出双层导航栏（world-bar 18px + view-bar 60px + 间距 ≈ 100px）
    // 下方留出 ribbon / view 切换栏（≈ 88px）
    el.style.left = `${clamp(cx, w / 2 + 18, innerWidth - w / 2 - 18)}px`;
    el.style.top  = `${clamp(cy, h / 2 + 100, innerHeight - h / 2 - 88)}px`;
  }

  function placeBubbles(bubbleEls) {
    const n = bubbleEls.length;
    if (!n) return;

    const m = detailLayoutMetrics();
    const leftX = clamp(
      m.centerX - m.imageW / 2 - BUBBLE_W / 2 - 88,
      BUBBLE_W / 2 + 58,
      m.simLeft - BUBBLE_W / 2 - 56
    );
    const topY = m.centerY - m.imageH / 2 - BUBBLE_H / 2 - 42;
    const bottomY = m.centerY + m.imageH / 2 + BUBBLE_H / 2 + 42;
    const topX = clamp(m.centerX + 92, BUBBLE_W / 2 + 22, m.simLeft - BUBBLE_W / 2 - 70);
    const bottomX = clamp(m.centerX + 40, BUBBLE_W / 2 + 22, m.simLeft - BUBBLE_W / 2 - 90);

    const leftCount = Math.max(0, n - 2);
    const leftTotalH = leftCount * BUBBLE_H + Math.max(0, leftCount - 1) * BUBBLE_GAP;
    const leftStartY = m.centerY - leftTotalH / 2 + BUBBLE_H / 2;

    const slots = [];
    if (n === 1) {
      slots.push([leftX, m.centerY]);
    } else {
      for (let i = 0; i < leftCount; i++) {
        slots.push([leftX, leftStartY + i * (BUBBLE_H + BUBBLE_GAP)]);
      }
      slots.push([topX, topY]);
      slots.push([bottomX, bottomY]);
    }

    bubbleEls.forEach((el, i) => {
      const [cx, cy] = slots[i] || [leftX, m.centerY];
      applyElementCenter(el, cx, cy, BUBBLE_W, BUBBLE_H);
    });
  }

  function placeCards(cardEls) {
    const n = cardEls.length;
    if (!n) return;

    const m = detailLayoutMetrics();
    const totalH = n * CARD_H + (n - 1) * CARD_GAP;
    const startY = m.centerY - totalH / 2;

    cardEls.forEach((el, i) => {
      const cy = startY + i * (CARD_H + CARD_GAP) + CARD_H / 2;
      applyElementCenter(el, m.simX, cy, CARD_W, CARD_H);
    });
  }

  // ─── 选中展品 ─────────────────────────────────────────────────────────────
  function selectExhibit(index) {
    state.selectedIndex = index;
    state.hoveredIndex  = index;
    clearLabels();

    const ex      = EXHIBITS[index];
    const world   = state.currentWorld;
    const vk      = currentViewKey();
    updateImagePanel(ex, world, vk);

    // Unfinished world: skip narrative bubbles; hand off to unfinished-world.js via event
    if (world === "unfinished") {
      document.dispatchEvent(new CustomEvent("uwExhibitSelect", { detail: { exhibit: ex, index } }));
    } else {
      const narratives = getNarratives(ex, world, vk).slice(0, 6);
      const items = narratives.length ? narratives : [{ key: state.currentView, val: "No extracted text in this dimension." }];
      items.forEach((item, i) => {
        const el = document.createElement("div");
        el.className = `kw-bubble ${WORLD_CONFIG[world].className}`;
        el.dataset.kind  = "bubble";
        el.dataset.index = String(i);
        el.innerHTML = `
          <span class="bubble-field">${escapeHtml(item.key || state.currentView)}</span>
          <span class="bubble-value">${escapeHtml(item.val || item.value || item.text || "")}</span>
        `;
        els.labels.appendChild(el);
        state.labels.push(el);
        requestAnimationFrame(() => el.classList.add("shown"));
      });
    }

    getSimilarIds(ex).slice(0, 3).forEach((ti, i) => {
      const tgt = EXHIBITS[ti];
      if (!tgt) return;

      const card = document.createElement("button");
      card.type = "button";
      card.className = "sim-card";
      card.dataset.kind        = "similar";
      card.dataset.index       = String(i);
      card.dataset.targetIndex = String(ti);
      card.innerHTML = `
        <div class="sim-card-label">Adjacent work</div>
        <div class="sim-card-name">${escapeHtml(tgt.name)}</div>
        <div class="sim-card-reason">${escapeHtml(getSimilarReason(ex, ti))}</div>
      `;
      card.addEventListener("click", ev => {
        ev.preventDefault(); ev.stopPropagation();
        selectExhibit(ti);
      });
      els.labels.appendChild(card);
      state.labels.push(card);
      requestAnimationFrame(() => card.classList.add("shown"));
    });

    els.deselectHint.classList.add("on");
    els.tip.style.opacity = "0";
  }

  function deselectExhibit() {
    state.selectedIndex = -1;
    state.hoveredIndex  = -1;
    clearLabels();
    hideImagePanel();
    els.deselectHint.classList.remove("on");
    els.tip.style.opacity = "0";
    document.body.style.cursor = "default";
    document.dispatchEvent(new CustomEvent("uwExhibitDeselect"));
  }

  // ─── 世界连接桥 ───────────────────────────────────────────────────────────
  function rebuildWorldBridge() {
    while (bridgeGroup.children.length) bridgeGroup.remove(bridgeGroup.children[0]);

    const anchors = {
      official: new THREE.Vector3(...WORLD_CONFIG.official.offset),
      staged:   new THREE.Vector3(...WORLD_CONFIG.staged.offset),
      lived:    new THREE.Vector3(...WORLD_CONFIG.lived.offset)
    };

    [["official","staged"],["staged","lived"],["lived","official"]].forEach(([a,b]) => {
      const start = anchors[a], end = anchors[b];
      const mid   = start.clone().add(end).multiplyScalar(0.5);
      mid.y += 0.8;

      const curve = new THREE.QuadraticBezierCurve3(start, mid, end);
      const geo   = new THREE.BufferGeometry().setFromPoints(curve.getPoints(32));
      const mat   = new THREE.LineBasicMaterial({
        color: WORLD_CONFIG[a].color.clone().lerp(WORLD_CONFIG[b].color, 0.5),
        transparent: true,
        opacity: 0.20,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      bridgeGroup.add(new THREE.Line(geo, mat));
    });
  }

  // ─── 布局应用 ─────────────────────────────────────────────────────────────
  function applyLayout() {
    if (!state.currentWorld) return;

    EXHIBITS.forEach((ex, i) => {
      const base = getBasePosition(ex, state.currentWorld, currentViewKey());
      const p    = orbitTransform(state.currentWorld, base, i);
      state.targets[i].set(p[0], p[1], p[2]);

      const bc      = new THREE.Color(ex.color || "#ffffff");
      const density = getDensity(ex, state.currentWorld, currentViewKey());
      const tone    = bc.clone().lerp(activeColor(), WORLD_CONFIG[state.currentWorld].pointTint + density * 0.18);
      state.meshes[i].material.color.copy(tone);
      state.meshes[i].userData.halo.material.color.copy(tone);
      state.meshes[i].userData.density = density;
    });

    document.body.dataset.world = state.currentWorld;
    document.querySelectorAll(".wb").forEach(b => b.classList.toggle("active", b.dataset.world === state.currentWorld));
    document.querySelectorAll(".vb").forEach(b => b.classList.toggle("active", b.dataset.view  === state.currentView));
    const ribbon = document.getElementById("expo-ribbon");
    const viewLabel = state.currentView.charAt(0).toUpperCase() + state.currentView.slice(1);
    if (ribbon) ribbon.textContent = `${WORLD_CONFIG[state.currentWorld].label}  ·  ${viewLabel}`;

    // 幽灵背景文字（世界名第一个词，作为大气水印）
    if (els.worldGhost) {
      const ghostWords = { official: "Official", staged: "Staged", lived: "Lived", unfinished: "Unfinished" };
      els.worldGhost.textContent = ghostWords[state.currentWorld] || "";
    }

    els.intro.classList.add("hidden");
    els.worldBar.classList.add("on");
    els.viewBar.classList.add("on");
    if (els.modeToggle) els.modeToggle.classList.add("on");
    rebuildWorldBridge();
    // 重建点形态 SVG（世界/视角变化时形态随之改变）
    rebuildPointSVGs();
  }

  function setWorld(world) {
    const keepSelectedIndex = state.selectedIndex;
    state.currentWorld = world;
    clearLabels();
    state.hoveredIndex = keepSelectedIndex;
    els.tip.style.opacity = "0";
    applyLayout();

    if (keepSelectedIndex >= 0) {
      selectExhibit(keepSelectedIndex);
    } else {
      state.selectedIndex = -1;
      state.hoveredIndex = -1;
      els.deselectHint.classList.remove("on");
    }
  }

  function setView(view) {
    state.currentView = view;
    document.querySelectorAll(".vb").forEach(b => b.classList.toggle("active", b.dataset.view === view));
    const ribbon = document.getElementById("expo-ribbon");
    if (ribbon && state.currentWorld) {
      const vl = view.charAt(0).toUpperCase() + view.slice(1);
      ribbon.textContent = `${WORLD_CONFIG[state.currentWorld].label}  ·  ${vl}`;
    }
    clearLabels();
    applyLayout();
    if (state.selectedIndex >= 0) selectExhibit(state.selectedIndex);
  }

  // ─── 点位层更新（缩略图 + 密度尺寸 + SVG 状态驱动） ─────────────────────
  function updatePointLayer() {
    const hasWorld = !!state.currentWorld;
    EXHIBITS.forEach((ex, i) => {
      const pt   = state.pointEls[i];
      const mesh = state.meshes[i];

      if (!hasWorld) { pt.classList.add("hidden"); return; }

      const proj = project(mesh.position, camera);
      if (proj.z <= -1 || proj.z >= 1) { pt.classList.add("hidden"); return; }

      const isSel  = state.selectedIndex === i;
      const isHov  = state.hoveredIndex  === i;
      const isSim  = state.selectedIndex >= 0 && getSimilarIds(EXHIBITS[state.selectedIndex]).includes(i);
      const density = mesh.userData.density ?? getDensity(ex, state.currentWorld, currentViewKey());

      // 密度决定基础尺寸：24px（稀疏）→ 78px（核心）
      const baseSize = Math.round(36 + density * 72);   // 36–108 px (was 24–78)
      const hitSize  = isSel ? Math.min(Math.round(baseSize * 1.28), 148)
                     : isHov ? Math.round(baseSize * 1.18)
                     : baseSize;

      // 整体透明度
      const baseOpacity = 0.55 + density * 0.36;
      const opacity = state.selectedIndex < 0
        ? baseOpacity
        : isSel ? 1.0
        : isSim ? 0.90
        : 0.12;

      pt.classList.remove("hidden");
      pt.style.left    = `${proj.x}px`;
      pt.style.top     = `${proj.y}px`;
      pt.style.width   = `${hitSize}px`;
      pt.style.height  = `${hitSize}px`;
      pt.style.opacity = String(opacity);
      pt.style.transform = "translate(-50%,-50%)";

      pt.classList.toggle("selected", isSel);
      pt.classList.toggle("hovered",  isHov && !isSel);
      pt.classList.toggle("similar",  isSim && !isSel);

      // ── 点位图像懒加载（图像模式且高密度展品才加载） ────────────────────────
      const thumbEl = pt.querySelector(".point-thumb");
      if (thumbEl && !thumbEl.dataset.attempted && state.pointMode === "images" && density >= 0.46) {
        thumbEl.dataset.attempted = "1";
        const src = getRestoredImagePath(ex);
        if (src) {
          thumbEl.onload  = () => { thumbEl.classList.add("loaded"); pt.classList.add("img-loaded"); };
          thumbEl.onerror = () => { thumbEl.style.display = "none"; };
          thumbEl.src = src;
        } else {
          thumbEl.style.display = "none";
        }
      }
    });
  }

  // ─── 标签 & 连线更新（核心：无重叠布局） ──────────────────────────────────
  function updateLabels() {
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    if (state.selectedIndex < 0) return;

    const origin    = { x: innerWidth / 2, y: innerHeight / 2 };
    const color     = activeColor();
    const bubbleEls = state.labels.filter(el => el.dataset.kind === "bubble");
    const simEls    = state.labels.filter(el => el.dataset.kind === "similar");

    // 精确布局
    placeBubbles(bubbleEls, origin.x, origin.y);
    placeCards(simEls, origin.x, origin.y);

    // ── 绘制连线：从选中点到气泡/卡片，用优雅曲线 ──────────────────────────
    ctx.save();
    ctx.setLineDash([3, 7]);
    ctx.lineWidth = 1.0;

    bubbleEls.forEach(el => {
      const bx = parseFloat(el.style.left);
      const by = parseFloat(el.style.top);
      // 气泡右边缘连到 origin
      const ex2 = bx + BUBBLE_W / 2 + 2;
      const ey  = by;
      ctx.beginPath();
      ctx.strokeStyle = colorToCss(color, 0.28);
      // 柔和贝塞尔曲线
      const mx = (ex2 + origin.x) / 2;
      ctx.moveTo(ex2, ey);
      ctx.quadraticCurveTo(mx, ey, origin.x, origin.y);
      ctx.stroke();
    });

    simEls.forEach(el => {
      const cx  = parseFloat(el.style.left);
      const cy  = parseFloat(el.style.top);
      const ti  = Number(el.dataset.targetIndex ?? -1);
      // 卡片左边缘连到目标展品
      const ex2 = cx - CARD_W / 2 - 2;

      // 主线：选中点 → 卡片
      ctx.beginPath();
      ctx.strokeStyle = colorToCss(color, 0.32);
      const mx = (origin.x + ex2) / 2;
      ctx.moveTo(origin.x, origin.y);
      ctx.quadraticCurveTo(mx, origin.y, ex2, cy);
      ctx.stroke();

      // 虚线：目标展品 → 卡片
      if (ti >= 0) {
        const tgt = project(state.meshes[ti].position, camera);
        ctx.beginPath();
        ctx.setLineDash([2, 6]);
        ctx.strokeStyle = colorToCss(color, 0.18);
        ctx.moveTo(tgt.x, tgt.y);
        ctx.lineTo(ex2, cy);
        ctx.stroke();
        ctx.setLineDash([3, 7]);
      }
    });

    ctx.restore();
  }

  // ─── 事件绑定 ─────────────────────────────────────────────────────────────
  function bindEvents() {
    document.querySelectorAll(".ve").forEach(btn => {
      btn.addEventListener("click", () => setWorld(btn.dataset.world));
    });
    document.querySelectorAll(".wb").forEach(btn => {
      btn.addEventListener("click", ev => { ev.stopPropagation(); setWorld(btn.dataset.world); });
    });
    document.querySelectorAll(".vb").forEach(btn => {
      btn.addEventListener("click", ev => { ev.stopPropagation(); setView(btn.dataset.view); });
    });
    els.deselectHint.addEventListener("click", ev => { ev.stopPropagation(); deselectExhibit(); });

    // ── 显示模式切换 ────────────────────────────────────────────────────────
    document.querySelectorAll(".mt").forEach(btn => {
      btn.addEventListener("click", ev => {
        ev.stopPropagation();
        const mode = btn.dataset.mode;
        if (state.pointMode === mode) return;
        state.pointMode = mode;
        document.querySelectorAll(".mt").forEach(b => b.classList.toggle("active", b.dataset.mode === mode));
        document.body.classList.toggle("point-mode-dots",   mode === "dots");
        document.body.classList.toggle("point-mode-images", mode === "images");
      });
    });

    renderer.domElement.addEventListener("pointerdown", ev => {
      state.dragging = true;
      state.dragMoved = false;
      state.dragStart = { x: ev.clientX, y: ev.clientY };
      renderer.domElement.setPointerCapture(ev.pointerId);
      document.body.style.cursor = "grabbing";
    });
    renderer.domElement.addEventListener("pointermove", ev => {
      if (!state.dragging) return;
      const dx = ev.clientX - state.dragStart.x;
      const dy = ev.clientY - state.dragStart.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) state.dragMoved = true;
      state.camTargetTheta = wrap360(state.camTargetTheta - dx * 0.004);
      state.dragStart = { x: ev.clientX, y: ev.clientY };
    });
    renderer.domElement.addEventListener("pointerup", ev => {
      state.dragging = false;
      renderer.domElement.releasePointerCapture(ev.pointerId);
      document.body.style.cursor = "default";
      if (!state.dragMoved && state.selectedIndex >= 0) deselectExhibit();
    });
    renderer.domElement.addEventListener("wheel", ev => {
      ev.preventDefault();
      state.camTargetFov = clamp(state.camTargetFov + ev.deltaY * 0.025, 38.0, 82.0);
    }, { passive: false });
    document.addEventListener("keydown", ev => { if (ev.key === "Escape") deselectExhibit(); });
    window.addEventListener("resize", () => {
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
      resizeConnector();
    });
  }

  // ─── 动画循环 ─────────────────────────────────────────────────────────────
  function animate() {
    requestAnimationFrame(animate);
    const t = performance.now() * 0.001;

    if (!state.dragging) state.camTargetTheta = wrap360(state.camTargetTheta + 0.00040);

    state.camTheta  += (state.camTargetTheta - state.camTheta)  * 0.038;
    state.camPhi    += (state.camTargetPhi   - state.camPhi)    * 0.038;
    state.camRadius += (state.camTargetRadius - state.camRadius) * 0.080;
    state.camFov    += (state.camTargetFov    - state.camFov)    * 0.080;

    camera.fov = state.camFov;
    camera.updateProjectionMatrix();
    camera.position.set(0, 0, 0);
    camera.lookAt(
      Math.sin(state.camPhi) * Math.sin(state.camTheta),
      Math.cos(state.camPhi),
      Math.sin(state.camPhi) * Math.cos(state.camTheta)
    );

    stars.rotation.y = t * 0.009;
    stars.rotation.x = Math.sin(t * 0.07) * 0.028;

    state.meshes.forEach((mesh, i) => {
      if (state.currentWorld) {
        mesh.position.lerp(state.targets[i], 0.038);
      } else {
        mesh.position.x += Math.sin(t * 0.37 + i) * 0.018 - mesh.position.x * 0.0004;
        mesh.position.y += Math.cos(t * 0.29 + i * 1.1) * 0.015 - mesh.position.y * 0.0004;
        mesh.position.z += Math.sin(t * 0.43 + i * 0.7) * 0.014 - mesh.position.z * 0.0004;
      }

      const isSel  = state.selectedIndex === i;
      const isHov  = state.hoveredIndex  === i;
      const isSim  = state.selectedIndex >= 0 && getSimilarIds(EXHIBITS[state.selectedIndex]).includes(i);
      const density = mesh.userData.density ?? 0.3;

      // Three.js mesh 仅维持颜色供 colorToHex 读取，无可见几何体
      // 视觉效果由 SVG 点层 + CSS 动画承载
    });

    updatePointLayer();
    updateLabels();
    renderer.render(scene, camera);
  }

  // 初始化显示模式
  document.body.classList.add("point-mode-dots");

  bindEvents();
  makeMeshes();
  makePointLayer();

  // 点位图像替代环境标签层——不再使用独立的 ambient DOM 层
  state.nameLabelEls = new Array(EXHIBITS.length).fill(null);

  const params = new URLSearchParams(window.location.search);
  const reqView  = params.get("view");
  const reqWorld = params.get("world");

  if (reqView && VIEW_TO_KEY[reqView]) {
    state.currentView = reqView;
    document.querySelectorAll(".vb").forEach(b => b.classList.toggle("active", b.dataset.view === reqView));
  }
  if (reqWorld && WORLD_CONFIG[reqWorld]) setWorld(reqWorld);

  animate();

  // ─── 星空动画：闪烁星星 + 流星 ──────────────────────────────────────────────
  (function initStarField() {
    const canvas = document.getElementById("star-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    function resize() {
      canvas.width  = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    // 500 颗背景星 — 3 层：密集小星 / 中型闪烁 / 偶尔明亮
    const STAR_COUNT = 500;
    const stars = Array.from({ length: STAR_COUNT }, () => {
      const tier = Math.random();
      return {
        x:     Math.random(),
        y:     Math.random(),
        r:     tier < 0.65 ? Math.random() * 0.6 + 0.12           // 小星
              : tier < 0.92 ? Math.random() * 1.0 + 0.55          // 中型
              : Math.random() * 1.6 + 1.2,                         // 明亮
        base:  tier < 0.65 ? 0.08 + Math.random() * 0.28
              : tier < 0.92 ? 0.20 + Math.random() * 0.45
              : 0.55 + Math.random() * 0.38,
        phase: Math.random() * Math.PI * 2,
        freq:  0.00010 + Math.random() * 0.00070
      };
    });

    // 流星队列 — 更频繁、更亮、更长
    const shoots = [];
    let nextShootAt = performance.now() + 1200 + Math.random() * 2500;

    function spawnShoot(now) {
      shoots.push({
        x:        Math.random() * 0.82 + 0.04,
        y:        Math.random() * 0.42,
        len:      0.10 + Math.random() * 0.16,        // 更长拖尾
        spd:      0.00028 + Math.random() * 0.00032,
        angle:    Math.PI / 5 + Math.random() * Math.PI / 7,
        progress: 0,
        alpha:    0.75 + Math.random() * 0.24,
        width:    1.0 + Math.random() * 1.2           // 粗细随机
      });
      nextShootAt = now + 2800 + Math.random() * 5500; // 更频繁
    }

    function draw(now) {
      const w = canvas.width, h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      // ── 闪烁星星 ──
      stars.forEach(s => {
        const a = s.base * (0.45 + 0.55 * Math.sin(s.phase + now * s.freq));
        ctx.beginPath();
        ctx.arc(s.x * w, s.y * h, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`;
        ctx.fill();
      });

      // ── 流星 ──
      if (now >= nextShootAt) spawnShoot(now);

      for (let i = shoots.length - 1; i >= 0; i--) {
        const s = shoots[i];
        s.progress = Math.min(1, s.progress + s.spd * 16);

        const headX = (s.x + Math.cos(s.angle) * s.len * s.progress) * w;
        const headY = (s.y + Math.sin(s.angle) * s.len * s.progress) * h;
        const tailT = Math.max(0, s.progress - 0.14);
        const tailX = (s.x + Math.cos(s.angle) * s.len * tailT) * w;
        const tailY = (s.y + Math.sin(s.angle) * s.len * tailT) * h;

        // 尾部淡出
        const fade = s.progress > 0.78 ? (1 - s.progress) / 0.22 : 1;
        const g = ctx.createLinearGradient(tailX, tailY, headX, headY);
        g.addColorStop(0, "rgba(255,255,255,0)");
        g.addColorStop(1, `rgba(255,255,255,${(s.alpha * fade).toFixed(3)})`);

        ctx.beginPath();
        ctx.moveTo(tailX, tailY);
        ctx.lineTo(headX, headY);
        ctx.strokeStyle = g;
        ctx.lineWidth = s.width;
        // 流星光晕
        ctx.shadowBlur = 6;
        ctx.shadowColor = `rgba(255,255,255,${(s.alpha * fade * 0.6).toFixed(3)})`;
        ctx.stroke();
        ctx.shadowBlur = 0;

        if (s.progress >= 1) shoots.splice(i, 1);
      }

      requestAnimationFrame(draw);
    }

    requestAnimationFrame(draw);
  })();

})();









