import { normalizeKey } from "./utils.js";

const DATA_DIR = "./outputs/mineru_triview_gemini_rerank_merge_full_v2";

export const WORLD_TO_DATASET = {
  official: "official",
  staged: "institutional",
  lived: "personal"
};

export const DATASET_TO_WORLD = {
  official: "official",
  institutional: "staged",
  staged: "staged",
  personal: "lived",
  lived: "lived"
};

export const VIEW_ALIASES = {
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

async function fetchText(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Cannot load ${path}: ${response.status} ${response.statusText}`);
  }
  return response.text();
}

function parseJsonl(text) {
  return text
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => JSON.parse(line));
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let insideQuote = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    const next = text[i + 1];

    if (ch === '"' && insideQuote && next === '"') {
      cell += '"';
      i++;
      continue;
    }

    if (ch === '"') {
      insideQuote = !insideQuote;
      continue;
    }

    if (ch === "," && !insideQuote) {
      row.push(cell);
      cell = "";
      continue;
    }

    if ((ch === "\n" || ch === "\r") && !insideQuote) {
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
    if (obj && obj[key] !== undefined && obj[key] !== null && obj[key] !== "") {
      return obj[key];
    }
  }
  return undefined;
}

function getExhibitId(row) {
  return String(firstDefined(row, [
    "product_id",
    "exhibit_id",
    "id",
    "profile_id",
    "object_id",
    "item_id",
    "index"
  ]) ?? "").trim();
}

function getExhibitName(row) {
  return String(firstDefined(row, [
    "name",
    "title",
    "product_name",
    "exhibit_name",
    "object_name",
    "label"
  ]) ?? "Untitled exhibit").trim();
}

function getWorld(row) {
  const raw = firstDefined(row, [
    "world",
    "discourse",
    "voice",
    "source_world",
    "embedding_world",
    "archive"
  ]);
  return DATASET_TO_WORLD[normalizeKey(raw)] || DATASET_TO_WORLD[String(raw ?? "").trim()] || "official";
}

function getView(row) {
  const raw = firstDefined(row, [
    "view",
    "field",
    "dimension",
    "aspect",
    "embedding_type",
    "analysis_type"
  ]);
  return VIEW_ALIASES[normalizeKey(raw)] || "overall";
}

function getCoordinate(row, keys, fallback = 0) {
  const value = firstDefined(row, keys);
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function getTextValue(row) {
  return String(firstDefined(row, [
    "text",
    "value",
    "summary",
    "quote",
    "content",
    "chunk",
    "description",
    "narrative"
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
        if (typeof item === "string") {
          result.push({ key: view, val: item });
        } else if (item && typeof item === "object") {
          result.push({
            key: item.key || item.label || view,
            val: item.val || item.value || item.text || item.summary || ""
          });
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
    narratives: {
      official: {},
      staged: {},
      lived: {}
    },
    pos: {
      official: {},
      staged: {},
      lived: {}
    },
    similar: {
      official: {},
      staged: {},
      lived: {}
    }
  };
}

function addNarrativeFromEmbedding(exhibit, world, view, row) {
  const text = getTextValue(row);
  if (!text) return;
  if (!exhibit.narratives[world]) exhibit.narratives[world] = {};
  if (!exhibit.narratives[world][view]) exhibit.narratives[world][view] = [];
  exhibit.narratives[world][view].push({
    key: view,
    val: text
  });
}

function addProfileFallbackNarratives(exhibit) {
  for (const world of ["official", "staged", "lived"]) {
    for (const view of ["overall", "technical", "category", "exhibition", "perception"]) {
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

  for (const list of result.values()) {
    list.sort((a, b) => b.score - a.score);
  }

  return result;
}

function fillSimilarityFromMatrix(exhibits, csvRows, idToIndex) {
  const edgeMap = readSimilarityRows(csvRows, idToIndex);

  for (const ex of exhibits) {
    for (const world of ["official", "staged", "lived"]) {
      for (const view of ["overall", "technical", "category", "exhibition", "perception"]) {
        const key = `${ex.id}|${world}|${view}`;
        const matches = edgeMap.get(key) || edgeMap.get(`${ex.id}|official|overall`) || [];
        ex.similar[world][view] = matches.slice(0, 8).map(item => item.targetIndex);
      }
    }
  }
}

function fillSimilarityFromDistance(exhibits) {
  for (const world of ["official", "staged", "lived"]) {
    for (const view of ["overall", "technical", "category", "exhibition", "perception"]) {
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

export async function loadExpoData(dataDir = DATA_DIR) {
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
      const view = getView(row);
      addNarrativeFromEmbedding(exhibits[idx], world, view, row);
    }
  }

  const umapRows = parseJsonl(umapText);
  for (const row of umapRows) {
    const id = getExhibitId(row);
    const idx = idToIndex.get(id);
    if (idx === undefined) continue;

    const world = getWorld(row);
    const view = getView(row);
    const x = getCoordinate(row, ["x", "umap_x", "coord_x", "0"]);
    const y = getCoordinate(row, ["y", "umap_y", "coord_y", "1"]);
    const z = getCoordinate(row, ["z", "umap_z", "coord_z", "2"], 0);

    exhibits[idx].pos[world][view] = [x, y, z];
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

  if (similarityText.trim()) {
    fillSimilarityFromMatrix(exhibits, parseCsv(similarityText), idToIndex);
  }
  fillSimilarityFromDistance(exhibits);

  return exhibits;
}
