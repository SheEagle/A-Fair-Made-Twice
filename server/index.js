const express = require("express");
const cors    = require("cors");
const { Pool } = require("pg");

const app  = express();
const port = process.env.PORT || 3800;

/* ── Database ─────────────────────────────────────────────────────────── */
const pool = new Pool({
  host:     process.env.PG_HOST     || "localhost",
  port:     parseInt(process.env.PG_PORT || "5432"),
  database: process.env.PG_DB       || "parisexpo",
  user:     process.env.PG_USER     || "expo",
  password: process.env.PG_PASSWORD || "expo1867",
});

async function initDB() {
  const client = await pool.connect();
  try {
    await client.query(`
      CREATE TABLE IF NOT EXISTS comments (
        id           SERIAL PRIMARY KEY,
        exhibit_id   TEXT        NOT NULL,
        username     TEXT        NOT NULL DEFAULT 'Anonymous',
        country      TEXT        NOT NULL DEFAULT '',
        world        TEXT        NOT NULL DEFAULT 'visitor',
        content      TEXT        NOT NULL,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
      -- Safely add columns if table existed without them
      ALTER TABLE comments ADD COLUMN IF NOT EXISTS country      TEXT NOT NULL DEFAULT '';
      ALTER TABLE comments ADD COLUMN IF NOT EXISTS prompt_type  TEXT NOT NULL DEFAULT 'free';
      ALTER TABLE comments ADD COLUMN IF NOT EXISTS perspective  TEXT NOT NULL DEFAULT '';
      CREATE INDEX IF NOT EXISTS comments_exhibit_id_idx ON comments(exhibit_id);
    `);
    console.log("[db] schema ready");
  } finally {
    client.release();
  }
}

/* ── Middleware ───────────────────────────────────────────────────────── */
app.use(cors());
app.use(express.json());

/* ── Routes ──────────────────────────────────────────────────────────── */

// Health check
app.get("/api/health", (_req, res) => res.json({ ok: true }));

// GET /api/comments?exhibitId=XX[&limit=30]
app.get("/api/comments", async (req, res) => {
  const { exhibitId, limit = 50 } = req.query;
  if (!exhibitId) return res.status(400).json({ error: "exhibitId required" });
  try {
    const { rows } = await pool.query(
      `SELECT id, username, country, world, prompt_type, perspective, content, created_at
       FROM comments
       WHERE exhibit_id = $1
       ORDER BY created_at DESC
       LIMIT $2`,
      [exhibitId, Math.min(Number(limit), 200)]
    );
    res.json(rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "db error" });
  }
});

// POST /api/comments  { exhibitId, username, country, world, prompt_type, perspective, content }
app.post("/api/comments", async (req, res) => {
  const { exhibitId, username = "Anonymous", country = "", world = "visitor",
          prompt_type = "free", perspective = "", content } = req.body;
  if (!exhibitId || !content?.trim()) {
    return res.status(400).json({ error: "exhibitId and content required" });
  }
  const safeUsername    = String(username).slice(0, 80) || "Anonymous";
  const safeCountry     = String(country).slice(0, 80).trim();
  const safeContent     = String(content).slice(0, 2000).trim();
  const safeWorld       = ["official", "staged", "lived", "visitor"].includes(world) ? world : "visitor";
  const safePromptType  = ["observe", "imagine", "connect", "question", "free"].includes(prompt_type) ? prompt_type : "free";
  const safePerspective = String(perspective).slice(0, 80).trim();
  try {
    const { rows } = await pool.query(
      `INSERT INTO comments (exhibit_id, username, country, world, prompt_type, perspective, content)
       VALUES ($1, $2, $3, $4, $5, $6, $7)
       RETURNING id, username, country, world, prompt_type, perspective, content, created_at`,
      [String(exhibitId), safeUsername, safeCountry, safeWorld, safePromptType, safePerspective, safeContent]
    );
    res.status(201).json(rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "db error" });
  }
});

// GET /api/recent  — most recent comments across all exhibits
app.get("/api/recent", async (req, res) => {
  const { limit = 20 } = req.query;
  try {
    const { rows } = await pool.query(
      `SELECT id, exhibit_id, username, country, world, prompt_type, perspective, content, created_at
       FROM comments
       ORDER BY created_at DESC
       LIMIT $1`,
      [Math.min(Number(limit), 100)]
    );
    res.json(rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "db error" });
  }
});

/* ── Start ────────────────────────────────────────────────────────────── */
initDB()
  .then(() => {
    app.listen(port, () => console.log(`[api] listening on :${port}`));
  })
  .catch(err => {
    console.error("[db] init failed:", err.message);
    process.exit(1);
  });
