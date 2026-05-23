const fs = require("fs");

const htmlPath = "initial.html";
const csvLines = fs.readFileSync("RestoredStereoManifest.csv", "utf8").trim().split(/\r?\n/).slice(1);

function splitCSV(line) {
  const out = [];
  let cur = "";
  let q = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (q && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        q = !q;
      }
    } else if (ch === "," && !q) {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

const parsedRows = csvLines.map(splitCSV);
const includedRows = parsedRows.filter((r) => r[11] === "TRUE");
const rows = (includedRows.length >= 200 ? includedRows : parsedRows).slice(0, 200);
const palette = ["#4fc3f7", "#c5b4fb", "#80cbc4", "#ffcc80", "#ff8a80", "#b8e986", "#ffd1dc", "#d7a86e"];
const mediumHue = {
  Sculpture: 34,
  Machine: 202,
  "Painting Sculpture": 270,
  Painting: 300,
  Architecture: 46,
  View: 190,
  Specimen: 130
};

const mediums = [...new Set(rows.map((r) => r[5] || "Object"))];
const countries = [...new Set(rows.map((r) => r[3] || "Unknown"))];
const locations = [...new Set(rows.map((r) => r[4] || "Unknown"))];

const ring = (items, rx, ry, rz) =>
  new Map(items.map((m, i) => {
    const a = i / Math.max(1, items.length) * Math.PI * 2;
    return [m, [Math.cos(a) * rx, Math.sin(a) * ry, Math.sin(i * 0.83) * rz]];
  }));

const byMedium = ring(mediums, 2.15, 1.15, 1.05);
const byCountry = ring(countries, 2.75, 1.35, 1.2);
const byLocation = ring(locations, 2.45, 1.12, 1.55);

function n(v, scale) {
  const x = parseFloat(v);
  return Number.isFinite(x) ? Math.max(-2.9, Math.min(2.9, x / scale)) : 0;
}

const exhibits = rows.map((r, i) => {
  const medium = r[5] || "Object";
  const country = r[3] || "Unknown";
  const location = r[4] || "Unknown";
  const title = r[2] || `Exhibit ${i + 1}`;
  const mx = n(r[8], 70);
  const my = n(r[9], 70);
  const made = byMedium.get(medium);
  const is = byCountry.get(country);
  const belongs = byLocation.get(location);
  const seen = [mx, my, Math.sin(i * 0.37) * 1.35];

  return {
    id: i,
    archiveId: r[0],
    cardId: r[1],
    name: title,
    country,
    location,
    collection: r[6] || "Unknown collection",
    geolocated: r[7] || "Unknown",
    notes: r[10] || "",
    include: r[11] || "TRUE",
    type: medium,
    color: palette[i % palette.length],
    thumbHue: mediumHue[medium] ?? ((i * 37) % 360),
    keywords: {
      made: [{ t: medium, k: "official" }, { t: "CSV medium", k: "official" }, { t: "surface imagined", k: "personal" }],
      is: [{ t: title.slice(0, 28), k: "official" }, { t: country, k: "official" }, { t: "fair identity", k: "personal" }],
      belongs: [{ t: location, k: "official" }, { t: country, k: "official" }, { t: "mapped position", k: "personal" }],
      seen: [{ t: r[7] || "geolocated", k: "official" }, { t: (r[10] || "stereo trace").slice(0, 34), k: "personal" }]
    },
    similar: { made: [], is: [], belongs: [], seen: [] },
    simReason: {},
    pos: { made, is, belongs, seen },
    official: {},
    personal: {}
  };
});

function nearest(i, metric) {
  return exhibits
    .map((e, j) => (j === i ? null : { j, score: metric(exhibits[i], e) }))
    .filter(Boolean)
    .sort((a, b) => a.score - b.score)
    .slice(0, 3)
    .map((x) => x.j);
}

exhibits.forEach((ex, i) => {
  ex.similar.made = nearest(i, (a, b) => (a.type === b.type ? 0 : 4) + Math.abs(a.id - b.id) / 80);
  ex.similar.is = nearest(i, (a, b) => (a.country === b.country ? 0 : 5) + Math.abs(a.id - b.id) / 80);
  ex.similar.belongs = nearest(i, (a, b) => (a.location === b.location ? 0 : 5) + Math.abs(a.id - b.id) / 80);
  ex.similar.seen = nearest(i, (a, b) => {
    const ax = a.pos.seen[0] - b.pos.seen[0];
    const ay = a.pos.seen[1] - b.pos.seen[1];
    return Math.sqrt(ax * ax + ay * ay);
  });
  [...new Set([...ex.similar.made, ...ex.similar.is, ...ex.similar.belongs, ...ex.similar.seen])].forEach((j) => {
    ex.simReason[j] =
      exhibits[j].type === ex.type ? "same medium" :
      exhibits[j].location === ex.location ? "same exposition location" :
      exhibits[j].country === ex.country ? "same national/section label" :
      "nearby manifest coordinate";
  });
});

const replacement = `const EXHIBITS = ${JSON.stringify(exhibits, null, 2)};\n\nconst VIEW_COLORS`;
let html = fs.readFileSync(htmlPath, "utf8");
html = html.replace(/const EXHIBITS = \[[\s\S]*?\];\s*\n\s*const VIEW_COLORS/, replacement);
fs.writeFileSync(htmlPath, html);
console.log(`generated ${exhibits.length} exhibits`);
