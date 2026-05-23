# Museum Multi-Discourse Semantic System

This project turns long-form museum source texts into discourse-aware, view-specific exhibit representations for retrieval, clustering, visualization, and downstream curatorial systems. It uses Docker Qdrant for vector search and Ollama for query generation, metadata translation, and chunk-level extraction. PDF-to-Markdown parsing can run through MinerU and is cached locally before chunking and indexing.

## What The System Models

The pipeline keeps three discourse channels separate:

- `official`
- `personal`
- `institutional`

It then builds five semantic views for each discourse:

- `technical`
- `category`
- `exhibition`
- `perception`
- `overall`

The final semantic space is therefore `view × discourse`, for example:

- `technical_official_report`
- `technical_visitor_accounts`
- `perception_official_report`
- `perception_visitor_accounts`

The current repository also contains a `text/commentary/` folder. In this project it is treated as the more personal discourse channel and mapped into `visitor_accounts`.

## Multilingual Input, English Semantic Output

Source texts may be multilingual, but the semantic layer is normalized into English.

- Metadata can come from CSV or Excel.
- All original metadata columns are preserved in `raw_metadata`.
- Normalized exhibit fields are created for system use.
- Metadata is translated into concise English through local Ollama for query building, hover text, and embedding text.
- Extracted `value` fields are always requested in English.
- Retrieval queries are always English.
- View texts used for embeddings are English only.
- Evidence stays in the original source language and is never translated.

This split is important: the system keeps provenance faithful while making semantic comparison consistent across multilingual corpora.

## Document Parsing And Caching

PDFs are not assumed to contain clean English text layers, and the project now supports a MinerU-first parsing path.

- MinerU parses each PDF into Markdown.
- The Markdown is cached locally in `outputs/cache/mineru_markdown/`.
- Chunking runs on the cached Markdown, not on the original PDF.
- Chunk embeddings are then stored in a dedicated Qdrant collection.
- The collection is reused unless the parser mode, chunk settings, or source cache version changes.

This means the expensive path becomes:

`PDF -> Markdown cache -> chunks -> Qdrant`

In normal full runs, each stage is reused:

- document markdown cache is reused if the `.md` already exists
- `chunks.jsonl` is reused for full runs
- the Qdrant collection is reused if it already contains vectors

After the first pass, changing `top_k`, query logic, or extraction prompts should not require rebuilding the whole corpus.

## Why Embeddings Are Not Merged

The system does **not** merge embeddings across views or discourse types.

- Technical language, exhibition framing, and visitor perception encode different semantics.
- Official institutional discourse and visitor narrative discourse often emphasize different evidence and different absences.
- Merging them into one vector would hide curatorial differences, suppress discourse distance, and blur omission patterns.

Instead, each `view × discourse` pair gets its own text and its own embedding so that curators can compare:

- how official and visitor narratives diverge
- where one discourse is silent
- which exhibits cluster similarly in one view but not another

## Data Model

Each exhibit preserves the normalized fields below and all original metadata columns:

```json
{
  "exhibit_id": "101",
  "archive_id": "0",
  "card_id": "101",
  "title": "Last Days of Napoleon by Vincenzo Vela",
  "country": "Italian Fine Arts Section",
  "location": "Palais",
  "medium": "Sculpture",
  "collection": "Francois Brunet",
  "geolocated": "Confident",
  "raw_metadata": {
    "...": "all original columns are preserved here"
  }
}
```

`exhibit_id` defaults to `card_id` and falls back to `archive_id` or a row id when needed.

## Extraction Fields

Technical view:

- Manufacturing Process
- Structural Feature
- Material

Category view:

- Category Context
- Functional Role
- Comparative Context

Exhibition view:

- Exhibition Context
- National Context
- Discursive Role

Perception view:

- Audience Impression
- Evaluation
- Popularity
- Sensory Description

Every extracted field contains a concise English `value`, original-language `evidence`, and a `confidence` score.

## How The Local Pipeline Maps The Dify Workflow

The checked-in `paris.yml` Dify workflow is parsed and converted into a Python pipeline with the same core sequence:

1. metadata-driven query generation
2. top-k retrieval
3. iterative per-chunk JSON extraction

Cloud dependencies are replaced with local services by default:

- Dify retrieval becomes Qdrant vector search
- Dify LLM nodes become Ollama calls
- iterative extraction becomes chunk-by-chunk validated Python execution

Optional fallback:

- Gemini API can be enabled for query generation and/or extraction when local inference is too slow.
- Google also offers hosted access to Gemma through the Gemini API, including `gemma-3-27b-it`.

## Project Layout

```text
src/
  ingestion/
  retrieval/
  extraction/
  aggregation/
  analysis/
  visualization/
  llm/
  storage/
  cli/
docker/
  docker-compose.yml
outputs/
README.md
```

## Local Setup

### 1. Create a virtual environment and install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

### 2. Start Qdrant and Ollama with Docker

```powershell
docker compose -f docker/docker-compose.yml up -d
```

### 3. Pull a local Ollama model

Recommended:

```powershell
docker exec -it museum-ollama ollama pull qwen3:8b
```

Smaller fallback:

```powershell
docker exec -it museum-ollama ollama pull gemma3:4b
```

## Running The Pipeline

End-to-end run:

```powershell
python -m src.cli.main run
```

Useful options:

```powershell
python -m src.cli.main run --parser-provider mineru --qdrant-collection museum_exhibit_chunks_mineru
python -m src.cli.main run --ollama-model qwen3:8b --top-k 6
python -m src.cli.main run --top-k 10 --retrieval-candidate-k 20 --enable-rerank
python -m src.cli.main parse-dify --workflow-path paris.yml
```

Hosted Gemini / Gemma fallback:

```powershell
$env:GEMINI_API_KEY="your_key_here"
python -m src.cli.main run --llm-provider gemini --query-provider gemini --ollama-model gemma-3-27b-it --query-model gemma-3-27b-it
```

Environment variables can also override defaults:

- `QDRANT_URL`
- `QDRANT_COLLECTION`
- `OLLAMA_URL`
- `OLLAMA_MODEL`
- `LLM_PROVIDER`
- `QUERY_PROVIDER`
- `PARSER_PROVIDER`
- `QUERY_MODEL`
- `GEMINI_API_KEY`
- `GEMINI_BASE_URL`
- `MINERU_API_TOKEN`
- `MINERU_BASE_URL`
- `MINERU_MODEL_VERSION`
- `EMBEDDING_MODEL`
- `RERANKER_MODEL`
- `RETRIEVAL_CANDIDATE_K`
- `ENABLE_RERANK`
- `RERANK_BATCH_SIZE`
- `MUSEUM_METADATA_PATH`
- `MUSEUM_TEXTS_PATH`
- `MUSEUM_OUTPUTS_PATH`

## Retrieval Behavior

The retrieval stack is:

- one shared English query plan per exhibit
- dense vector retrieval in Qdrant for each discourse channel
- optional cross-encoder reranking on the merged dense candidates

`top_k` controls the final number of chunks kept for extraction.

`retrieval_candidate_k` controls how many dense candidates are gathered before reranking.

Example:

```powershell
python -m src.cli.main run --top-k 10 --retrieval-candidate-k 20 --enable-rerank
```

This means:

- retrieve up to 20 dense candidates in each discourse channel
- rerank them with the cross-encoder
- keep the best 10 for extraction

Hybrid dense+sparse retrieval is not enabled yet in this repository.

## Output Files

The pipeline writes:

- `outputs/chunks.jsonl`
- `outputs/retrieval_results.jsonl`
- `outputs/extraction_results.jsonl`
- `outputs/exhibit_profiles.jsonl`
- `outputs/exhibit_embeddings_official.jsonl`
- `outputs/exhibit_embeddings_personal.jsonl`
- `outputs/exhibit_embeddings_institutional.jsonl`
- `outputs/umap_coordinates.jsonl`
- `outputs/similarity_matrix.csv`
- `outputs/exhibit_map.html`
- `outputs/discourse_diff.csv`

These outputs are machine-readable and suitable for downstream 3D spatial systems, sonification or audio scripting, and custom curatorial interfaces.

## How To Interpret The Visualization

Open `outputs/exhibit_map.html` in a browser after a run.

- Use the `View` control to switch between technical, category, exhibition, perception, and overall projections.
- Use the `Discourse` control to switch between institutional and visitor semantic spaces.
- Hover over a point to see the English metadata layer and the extracted English field values.
- Distances represent similarity only within the currently selected `view × discourse` slice.

If two exhibits cluster together in `perception_visitor_accounts` but not in `technical_official_report`, that suggests public reception is aligning differently from institutional description.

## How To Interpret Discourse Differences

`outputs/discourse_diff.csv` is the curatorial comparison table.

It reports:

- `discourse_distance`: vector distance between official and visitor embeddings for the same exhibit and view
- `official_field_count`
- `visitor_field_count`
- `only_in_official`
- `only_in_visitor`

Use it to find:

- exhibits that are institutionally described but weakly perceived by visitors
- visitor impressions absent from official reporting
- strong technical overlap but large perception distance
- discourse gaps where one side contributes no evidence at all

## Notes On Robustness

- Chunking uses token windows of 400 with 60-token overlap by default.
- Qdrant collections are auto-created.
- Extraction uses Pydantic validation and retries.
- Missing metadata is allowed.
- Raw metadata schema can expand without code changes because all source columns are preserved.

## Suggested Next Extensions

- add incremental caching for translated metadata and extraction responses
- export 3D coordinates or scene-ready JSON for immersive viewers
- add audio narration templates from discourse-aware field summaries
- expose a small local API on top of the generated profile files
