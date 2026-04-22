# Stack Research — our-lady-book-pipeline

**Domain:** Autonomous LLM-based long-form creative-writing pipeline (fine-tuned local drafter + frontier critic + typed RAG + experiment telemetry + openclaw orchestration)
**Researched:** 2026-04-21
**Overall confidence:** HIGH on library selection + versions; MEDIUM on openclaw layout specifics (verified from installed docs + working `wipe-haus-state` example); HIGH on paul-thinkpiece-pipeline conventions (directly inspected)

---

## TL;DR (roadmap-ready)

| Concern | Pick | One-liner |
|---|---|---|
| Local inference | **vLLM 0.19+ (cu130 wheel/Docker)** | Same stack that already serves Gemma-4 for wipe-haus-state; best Qwen3 throughput on Blackwell |
| Vector store | **LanceDB 0.30+** | Embedded (no server), metadata filter primitive, fits 5-index × ≤500 rows trivially, survives reboots as files |
| Embeddings | **BGE-M3 (dense) via sentence-transformers**, served locally | Strong MTEB retrieval, 8K context clean, multi-func (dense+sparse+colbert) if we need hybrid later |
| Anthropic SDK | **`anthropic>=0.96.0`** | Opus 4.7 support, `client.messages.parse()` for typed outputs, ephemeral cache with 1h TTL |
| Observability | **stdlib `logging` + `python-json-logger` → JSONL**, opt-in Logfire later | Zero deps, works everywhere, ADR-003's `runs/events.jsonl` contract doesn't need a framework |
| Config | **Pydantic Settings 2 + `PyYAML` via custom YamlConfigSettingsSource** | All 4 config files type-checked at load; one source of truth for shapes |
| Packaging | **`uv` (pyproject.toml, `uv.lock`)** | Deliberate deviation from paul-thinkpiece-pipeline (which is bare venv+pip); see rationale below |
| Orchestration | **openclaw.json at repo root** (NOT `.openclaw/`), cron via `openclaw cron add`, agent workspaces under `workspaces/<agent>/` | Matches wipe-haus-state working pattern and openclaw v2026.4.5 docs |

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **Python** | 3.11 (match `venv_cu130`) | Runtime | Sibling `paul-thinkpiece-pipeline` standardizes on it; cu130 wheels target 3.11 |
| **vLLM** | 0.19.x+ (cu130 build, or NVIDIA's DGX Spark Docker image) | Local OpenAI-compatible server for Mode-A voice FT checkpoint | Already the working choice in-house — wipe-haus-state serves `gemma-4-26b-a4b` NVFP4 via vLLM at `127.0.0.1:8000/v1`. vLLM 0.19+ has CUDA 13 + SM_120/121a support, FlashAttention 4, and native Qwen3 family (8B→32B) parser. llama.cpp would lose structured-output speed on 32B; TGI has weaker CUDA-13 story. |
| **Anthropic Python SDK** | `anthropic>=0.96.0,<0.97` | Critic, entity extractor, retrospective writer, digest synthesis, Mode-B drafter | v0.96.0 (2026-04-16) adds `claude-opus-4-7`; `.messages.parse()` for schema-guaranteed JSON (critic rubric); `cache_control.ttl="1h"` for corpus cache on repeated critic calls |
| **LanceDB** | `lancedb>=0.30.2` | All 5 typed RAG indexes | Embedded — no Postgres or Qdrant container to maintain alongside vLLM+openclaw. Lance format = git-trackable columnar files under `indexes/`. Metadata `where` clauses are first-class (critical for date-range, POV-name, chapter-number filters). At our scale (5 × ≤500 rows ≈ 2.5K total vectors), performance is a non-question; deployment simplicity wins. |
| **BGE-M3** | `BAAI/bge-m3` via `sentence-transformers>=3.x` | Embedding model, one shared instance for all 5 retrievers | 568M params, MTEB retrieval ~63, stays clean to 8K tokens (most competitors degrade past 4K), multi-functionality (dense + sparse + ColBERT tokens from one forward pass — lets us add hybrid sparse later without re-indexing). Runs on Spark's iGPU in FP16 in ~2GB. No OpenAI dependency, no per-query cost. |
| **openclaw** | 2026.4.5 (already installed, `~/.npm-global/lib/node_modules/openclaw`) | Orchestration: cron, persistent workspaces, nightly drafting loop | Already systemd-managed + proven in wipe-haus-state. Its gateway owns session persistence; we don't reinvent it. |
| **PostgreSQL / SQLite** | SQLite 3.40+ (stdlib) | Metric ledger, thesis registry | SQLite is enough for per-chapter metrics + thesis state. No separate server. If ledger ever outgrows a single file, migrate to Postgres — but 27 chapters × few hundred events each = trivial. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---|---|---|---|
| **pydantic** | `pydantic>=2.10` | All structured data: critic rubric output, entity cards, thesis records, retriever query/response | Default for every JSON-shaped payload in the pipeline. One canonical definition → validation at LLM boundaries, at disk boundaries, at test boundaries. |
| **pydantic-settings** | `pydantic-settings>=2.7` | Typed config loading from YAML + env | Drives `config/voice_pin.yaml`, `rubric.yaml`, `rag_retrievers.yaml`, `mode_thresholds.yaml`. Use `CustomSource` pattern with `yaml.safe_load` (see install block). Alternatively `pydantic-settings-yaml` if we want `file:xxxx` secret placeholders. |
| **PyYAML** | `PyYAML>=6.0` | YAML parsing for config | Plain `safe_load`. `ruamel.yaml` only needed if we round-trip-edit YAML with preserved comments — not a pipeline requirement (configs are human-edited in editors, not LLM-rewritten). |
| **python-json-logger** | `>=3.x` | JSON-formatted stdlib logging handler | Pipes `logging.info({...})` into `runs/events.jsonl` lines. Per ADR-003, every LLM call emits one structured event; this is the path. No framework migration needed later if we add Logfire (it absorbs stdlib logging). |
| **sentence-transformers** | `>=3.3` | BGE-M3 driver | Ships with ONNX + safetensors; handles dense+sparse BGE-M3 outputs. |
| **httpx** | `>=0.27` | HTTP to local vLLM (OpenAI-compatible endpoint) + Anthropic (SDK uses it underneath) | Already a transitive dep; pin for consistent timeout behavior on cron-driven long runs. |
| **tenacity** | `>=9.x` | Retry with backoff on transient failures (vLLM 502 during load, Anthropic 529 overloads) | Drafter + critic + extractor all wrap their LLM calls. Small blast radius, big reliability win for 8-hour unattended nightly runs. |
| **rich** | `>=13.x` | Local diagnostic pretty-printing (not in prod event log) | Interactive debugging of critic reports; optional. |
| **pytest** + **pytest-asyncio** | latest | Test harness | Ablation harness is easier to write if it reuses pytest parametrization. |
| **xxhash** | `>=3.x` | Prompt-hash + output-hash for event log | Faster than hashlib SHA256 for non-cryptographic content fingerprints (ADR-003 requirement is dedup, not security). |
| **tiktoken** or **anthropic.count_tokens** | latest | Accurate token counts for the metric ledger | Anthropic SDK has `messages.count_tokens`; use that for Opus/Sonnet traffic. vLLM reports usage in its response body — just read it. |

### Development Tools

| Tool | Purpose | Notes |
|---|---|---|
| **uv** | Dependency management, venv creation, Python pinning | `uv venv --python 3.11 .venv && uv sync` — ~3s cold install; crushes Poetry on both speed and on cu130 nightly index handling (`[[tool.uv.index]]` supports PyTorch's custom URL cleanly) |
| **ruff** | Lint + format | Replaces black + isort + flake8; one config, fast |
| **mypy** | Static typing | Tight on `drafter/`, `critic/`, `rag/`, `observability/` modules (these are the kernel candidates per ADR-004) |
| **pre-commit** | Git hooks | Run ruff + mypy + yaml-validate before commit. Config drift is the cheapest class of bug to prevent. |

---

## Installation

```bash
# --- from repo root of our-lady-book-pipeline ---

# 1. Init with uv (pins Python 3.11 to match paul-thinkpiece-pipeline venv_cu130)
uv venv --python 3.11 .venv
source .venv/bin/activate

# 2. Core deps
uv add \
  "anthropic>=0.96.0,<0.97" \
  "pydantic>=2.10" \
  "pydantic-settings>=2.7" \
  "PyYAML>=6.0" \
  "lancedb>=0.30.2" \
  "sentence-transformers>=3.3" \
  "httpx>=0.27" \
  "tenacity>=9.0" \
  "python-json-logger>=3.0" \
  "xxhash>=3.0" \
  "tiktoken"

# 3. Dev deps
uv add --dev \
  "pytest>=8" \
  "pytest-asyncio" \
  "ruff" \
  "mypy" \
  "pre-commit" \
  "rich"

# 4. vLLM — NOT installed in this venv.
# vLLM runs as a systemd --user service (mirror wipe-haus-state pattern) using
# paul-thinkpiece-pipeline's venv_cu130 at /home/admin/finetuning/venv_cu130.
# Book pipeline talks to it over HTTP. Don't duplicate the vLLM install.
#
# To install/update vLLM inside venv_cu130:
#   source /home/admin/finetuning/cu130_env.sh
#   /home/admin/finetuning/venv_cu130/bin/pip install -U "vllm>=0.19.0"
# (Or use the NVIDIA DGX Spark Docker image — see alternatives below.)

# 5. Embedding model (one-time download, ~2GB)
uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|---|---|---|
| **vLLM** | llama.cpp + llama-cpp-python | If we ever needed CPU-only or MacBook dev loop. On DGX Spark GB10 (96GB unified, SM_121a) vLLM wins on throughput by ~3×, and we already have the cu130 infra sunk-cost. |
| **vLLM** | TGI (Text Generation Inference) | If we outgrow a single-machine deployment and need HF's managed infra. Not near-term. |
| **vLLM** | Ollama | Fine for quick eyeballing, but worse throughput vs vLLM on Blackwell per Allen Kuo's Apr 2026 benchmarks. Already-installed vLLM is the incumbent. |
| **LanceDB** | pgvector (inside SQLite) / sqlite-vec | Defensible minimalist choice if we want *everything* in one SQLite file. We're not there — LanceDB is still single-file-per-table and Lance columnar storage gives us cheap re-indexing on chapter commits. |
| **LanceDB** | Qdrant | If indexes grew to millions of vectors and filter complexity exploded. Neither condition applies: ≤500 rows/index is nothing, and filter shapes are simple (date range, POV name, chapter K). Adding a dedicated server is pure overhead at this scale. |
| **LanceDB** | ChromaDB | Simpler than LanceDB for pure dev-loop use, but weaker metadata filter performance (search results cite 5-8× overhead on combined filters). Our critic *needs* fast metadata filters on every scene request. LanceDB wins. |
| **LanceDB** | pgvector in Postgres | If we had an existing Postgres we had to use. We don't, and adding Postgres for 2.5K vectors is infrastructure without benefit. |
| **BGE-M3** | nomic-embed-text-v2 | Lighter (137M), faster, CPU-friendly — but weaker at long-context (degrades past 4K). Our retriever queries often include a scene beat paragraph (2-4K tokens of outline + prior scene summary). BGE-M3's clean 8K is worth the size cost, especially since we have the GPU already running. |
| **BGE-M3** | jina-embeddings-v3 | Near-tied on retrieval benchmarks and has nice late-chunking. Not bad — pick this if BGE-M3 disappoints on domain-specific (historical-fiction / metaphysics-rule-card) retrieval. Worth keeping as the thesis 005 ablation comparison. |
| **BGE-M3** | E5-large-v2 | Older, beaten on 2026 MTEB. Skip. |
| **BGE-M3** | OpenAI `text-embedding-3-large` | API dep we explicitly want to avoid per PROJECT.md local-inference preference. Skip. |
| **stdlib logging → JSONL** | structlog | Lovely library, but adds a dependency and a mental model. Our event schema is fixed by ADR-003; we don't need a mutable context-stack. |
| **stdlib logging → JSONL** | loguru | Great ergonomics but its JSON serializer is opinionated and its monkey-patch of stdlib is unfriendly to Logfire integration. Avoid. |
| **stdlib logging → JSONL** | Pydantic Logfire | Strong LLM observability story (OTel-backed, auto-traces Anthropic SDK calls). *Defer*, not reject: it has a free tier and a paid tier. In phase 1 we ship JSONL to disk; in a later phase (post-digest-working) we add Logfire as an additional handler if weekly digest authoring feels starved for traces. JSONL stays as source of truth. |
| **Pydantic Settings + YAML** | dynaconf | More config sources OOB (etcd, vault, etc.) — overkill, single-machine single-user pipeline. |
| **Pydantic Settings + YAML** | omegaconf / Hydra | Powerful for ML experiment sweeps, but encodes experiment semantics that fight our explicit `runs/ablations/` harness + thesis registry. Not worth the framework weight. |
| **uv** | pip + bare venv (like paul-thinkpiece-pipeline) | Paul's sibling project uses ad-hoc `pip install` with no lock file. Works for research code; painful for a 6-month-running cron-driven pipeline where reproducibility of "what was running on Tuesday" is a feature. Book pipeline is production-shaped, not experiment-shaped. |
| **uv** | poetry | Works, but 3-10× slower, no CUDA nightly index story as clean, and trending down in mindshare vs uv (2026 PyPI downloads: uv ~75M/mo, poetry ~66M/mo). |
| **uv** | pdm | Closest competitor philosophically. No compelling differentiator over uv for our use case. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|---|---|---|
| **LangChain / LlamaIndex as the backbone** | Both are fine libraries individually but become dependency magnets — pull in 40+ transitive deps, lock you into their abstractions, break on minor upgrades. The critic/drafter/RAG loop is ~10 focused functions; abstracting through LangChain's agent primitives adds noise, not leverage. ADR-004 "don't abstract until written twice" applies doubly to third-party abstractions we didn't write. | Raw Anthropic SDK + raw OpenAI client (against vLLM) + our own `rag/` module calling LanceDB directly. |
| **Instructor** (for structured outputs) | Useful *before* Anthropic's native Structured Outputs shipped (Nov 2025). Now redundant — `client.messages.parse(response_format=MyPydanticModel)` gets us the same thing first-party. | Native `anthropic.messages.parse()`. |
| **loguru** | Monkey-patches stdlib logging, harder to compose with OTel/Logfire later. | stdlib `logging` + `python-json-logger`. |
| **Embedding APIs (OpenAI, Voyage, Cohere)** | Extra API dep, per-query cost, and RAG will hit embeddings hard (every scene request → 5 retriever queries). We have a GPU; use it. | BGE-M3 local. |
| **Serverless vector DBs (Pinecone, Weaviate Cloud)** | Network hop, auth, cost, over-engineered for ~2.5K vectors on one machine. | LanceDB embedded. |
| **ChromaDB server mode** | Even their client/server doesn't pay off under 1M vectors. | LanceDB embedded. |
| **`.openclaw/` subdirectory naming** | Common misconception (guessed, not documented). Openclaw's own docs and the working `wipe-haus-state` install place `openclaw.json` at **repo root** and workspaces under `workspaces/<agent>/`. The `~/.openclaw/` path is for openclaw-the-tool's own config (cron jobs db, sessions, credentials) — *not* per-project. | `openclaw.json` at repo root; see orchestration section. |
| **Custom cron via systemd timer** | Openclaw has a built-in persistent cron (`openclaw cron add`, jobs survive restart at `~/.openclaw/cron/jobs.json`) and delivers output to channels. Don't shadow it with a parallel systemd-timer system. | `openclaw cron add --cron "0 2 * * *" --session isolated ...` per ORCH-01 requirement. |
| **vLLM inside our book-pipeline venv** | vLLM lives in paul-thinkpiece-pipeline's `venv_cu130` already and is served by systemd. Installing a second copy in our venv invites CUDA/arch mismatches and pins drift. | Talk to vLLM over HTTP. Our venv has no torch/CUDA deps. |
| **OmegaConf/Hydra for this project** | Implies experiment-framework semantics (overrides from CLI, structured sweeps). Our experiment semantics live in the thesis registry + ablation harness (ADR-003), not in the config loader. | Pydantic Settings. |
| **ruamel.yaml** | Only needed if tools will round-trip-edit YAML files programmatically. We don't — configs are human-edited. | PyYAML. |

---

## Stack Patterns by Variant

**If Mode-A voice checkpoint is Qwen3-8B (from V6 lineage):**
- vLLM flags: `--model /home/admin/finetuning/output/paul-v6-qwen3-8b-merged --dtype bfloat16 --max-model-len 8192 --port 8002`
- Fits in ~18GB, leaves headroom on the 96GB GB10 for other workloads
- Expect ~40-60 tok/s single-stream

**If Mode-A voice checkpoint is Qwen3-32B (from V6 lineage):**
- vLLM flags: `--model .../paul-v6-qwen3-32b-merged --dtype bfloat16 --max-model-len 8192 --port 8002 --gpu-memory-utilization 0.85`
- ~65GB footprint bf16, or ~35GB w/ FP8/NVFP4 (match NVFP4 pattern from wipe-haus-state's Gemma-4 config)
- If bf16 is too heavy to coexist with embedding model + vLLM-Gemma, quantize to FP8 at merge time

**If Mode-A checkpoint turns out to be Gemma-4-26B-A4B (already running for wipe-haus-state):**
- Reuse the existing vLLM service on port 8000; just add `voice_pin.yaml` entry pointing at it
- Zero extra GPU cost — the model's already loaded for the other workload

**If Spark's GPU is overcommitted during a nightly run:**
- Path A: Spawn vLLM on demand at cron start, shut down at cron end (slower — model load ~60s)
- Path B (recommended): Keep vLLM running 24/7 on a dedicated port (8002 for book pipeline's voice model, separate from wipe-haus-state's 8000), manage memory by running one voice vLLM at a time, pause via `systemctl --user stop vllm-book-voice.service` for training jobs (same pattern as `vllm-qwen122` in paul-thinkpiece-pipeline MEMORY.md)

---

## Openclaw integration (prescriptive)

### Repo layout under `our-lady-book-pipeline/`

```
our-lady-book-pipeline/
├── openclaw.json                        # <-- at repo root, mirrors wipe-haus-state
├── workspaces/
│   ├── drafter/                         # one openclaw agent per pipeline role
│   │   ├── AGENTS.md                    # operating instructions for the drafter agent
│   │   ├── SOUL.md                      # "you are the drafter; your only job is scene-level voice-faithful prose"
│   │   ├── BOOT.md                      # optional startup checklist
│   │   ├── HEARTBEAT.md                 # optional (drafter probably doesn't need heartbeat)
│   │   └── memory/YYYY-MM-DD.md         # daily notes per openclaw convention
│   ├── critic/
│   ├── regenerator/
│   ├── entity-extractor/
│   ├── retrospective-writer/
│   └── digest-generator/
├── agents/                              # optional: shared identity/skill definitions referenced by openclaw.json
├── .planning/                           # GSD artifacts (this file lives here)
├── docs/                                # ARCHITECTURE.md, ADRs
├── config/                              # typed pipeline config (non-openclaw)
│   ├── voice_pin.yaml
│   ├── rubric.yaml
│   ├── rag_retrievers.yaml
│   └── mode_thresholds.yaml
├── src/book_pipeline/                   # Python package (importable by openclaw agents via shell-out)
│   ├── drafter/
│   ├── critic/
│   ├── regenerator/
│   ├── rag/
│   ├── observability/
│   ├── orchestration/
│   └── ...
├── canon/   drafts/   indexes/          # artifact dirs from README
├── entity-state/  runs/  theses/
├── retrospectives/  digests/
├── pyproject.toml                       # uv-managed
└── uv.lock
```

### `openclaw.json` skeleton (mirror wipe-haus-state pattern, not invented)

```jsonc
{
  "meta": { "lastTouchedVersion": "2026.4.21" },
  "env": {
    "vars": {
      "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"
    }
  },
  "models": {
    "mode": "merge",
    "providers": {
      "vllm": {
        "baseUrl": "http://127.0.0.1:8002/v1",   // our dedicated voice vLLM port
        "apiKey": "vllm",
        "api": "openai-completions",
        "models": [{ "id": "paul-voice-v6-qwen3-32b", "name": "Paul Voice FT (pinned)", "contextWindow": 8192, "maxTokens": 2048 }]
      },
      "anthropic": {
        "baseUrl": "https://api.anthropic.com",
        "api": "anthropic-messages",
        "models": [
          { "id": "claude-opus-4-7", "name": "Claude Opus 4.7" },
          { "id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6" }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "workspace": "/home/admin/Source/our-lady-book-pipeline/workspaces",
      "compaction": { "mode": "safeguard" },
      "maxConcurrent": 2
    },
    "list": [
      { "id": "drafter", "workspace": ".../workspaces/drafter", "model": "vllm/paul-voice-v6-qwen3-32b" },
      { "id": "critic", "workspace": ".../workspaces/critic", "model": "anthropic/claude-opus-4-7" },
      { "id": "entity-extractor", "workspace": ".../workspaces/entity-extractor", "model": "anthropic/claude-opus-4-7" },
      { "id": "retrospective-writer", "workspace": ".../workspaces/retrospective-writer", "model": "anthropic/claude-opus-4-7" },
      { "id": "digest-generator", "workspace": ".../workspaces/digest-generator", "model": "anthropic/claude-opus-4-7" }
    ]
  },
  "gateway": {
    "port": 18790,  // pick non-conflicting with wipe-haus-state's 18789
    "mode": "local",
    "bind": "loopback",
    "auth": { "mode": "token", "token": "${OPENCLAW_GATEWAY_TOKEN}" }
  }
}
```

### Nightly cron (satisfies ORCH-01)

```bash
openclaw cron add \
  --name "book-pipeline:nightly-draft" \
  --cron "0 2 * * *" \
  --tz "America/New_York" \
  --session isolated \
  --session-agent drafter \
  --system-event "Run nightly drafting loop: pick next uncommitted scene, execute RAG → draft → critic → regen/escalate → commit. See workspaces/drafter/AGENTS.md for the loop spec." \
  --wake now
```

Openclaw persists this in `~/.openclaw/cron/jobs.json` and survives reboots. One cron entry per scheduled task (nightly draft, morning digest, weekly cleanup). No systemd timers.

### Critical constraint reminders

- **`openclaw.json` at repo root** — NOT `.openclaw/` (that's openclaw's own global state dir at `~/.openclaw/`).
- Workspaces are directories with AGENTS/SOUL/USER/BOOT/HEARTBEAT markdown files and a `memory/` subdir. These are the agent's *home*, and agents can write to them freely.
- The openclaw gateway is already running as a `systemctl --user` service on the Spark (same pattern as wipe-haus-state). We don't start/stop it — we add our `openclaw.json` and cron entries to the already-running instance.
- **Port collision check before go-live**: wipe-haus-state uses gateway port 18789 and vLLM port 8000. Book pipeline should pick different ports (e.g., 18790 for gateway, 8002 for voice vLLM).

---

## Version Compatibility

| Package A | Compatible With | Notes |
|---|---|---|
| `vllm>=0.19` | PyTorch 2.10+cu130 | Must source `cu130_env.sh` before `pip install vllm`. `TORCH_CUDA_ARCH_LIST=12.1a` already exported by that script. |
| `vllm>=0.19` | CUDA 13.0+ | SM_120/121a requires CUDA 13 nvcc (SM_12x is unknown to CUDA 12 toolchains). Matches Spark's `venv_cu130`. |
| `lancedb>=0.30` | Python 3.10-3.13 | Use 3.11 for paul-thinkpiece-pipeline parity. |
| `anthropic>=0.96` | Python 3.9+ | No lower-bound friction. |
| `anthropic>=0.96` | `claude-opus-4-7` | First SDK with this model ID (added in v0.96.0, 2026-04-16). |
| `sentence-transformers>=3.3` | `transformers>=4.47` | Standard transitive pin; uv will resolve. |
| `pydantic-settings>=2.7` | `pydantic>=2.10` | Settings 2.x requires Pydantic 2.x. |
| `openclaw 2026.4.5` | Node 22.14+ or Node 24 | Already installed + running. |

### Potential conflicts to watch

- **Embedding model GPU memory vs vLLM GPU memory.** On a 96GB unified-memory Spark, BGE-M3 at fp16 (~2GB) + Qwen3-32B vLLM (~65GB bf16 or ~35GB FP8) + wipe-haus-state's Gemma-4 (already ~50GB NVFP4) may contend. Plan: quantize our voice FT to FP8/NVFP4 at merge time if coexistence needed; otherwise serve voice vLLM on-demand and wipe-haus-state 24/7, or vice versa. MEMORY.md already has the "always check GPU before training/serving" rule — extend it to vLLM.
- **Anthropic SDK cache semantics change (2026-02-05).** Prompt caching became workspace-scoped. Plan per-pipeline workspace for the Anthropic account; reuse the corpus cache across all critic calls within a run by sending an identical ordered prefix.
- **LanceDB schema migrations** when we add new retriever columns mid-project: Lance supports add-column without re-embedding, but changing embedding dims requires re-index. Pin BGE-M3 revision in `config/rag_retrievers.yaml`.

---

## Confidence Assessment

| Area | Confidence | Reason |
|---|---|---|
| Local inference (vLLM) | HIGH | Working install proven via wipe-haus-state; cu130 infra documented in-repo; SDK versions verified via vLLM/NVIDIA docs |
| Vector DB (LanceDB) | HIGH | Version verified on PyPI; scale analysis is obvious at 5×500 rows; metadata-filter requirement explicit in RAG design |
| Embeddings (BGE-M3) | MEDIUM-HIGH | 2026 MTEB/benchmark data is consistent across 3+ independent reviews; only domain-specific retrieval quality is unverified (historical fiction + Nahuatl names + metaphysics rule-cards is non-standard corpus) — flag as thesis 005 (test vs jina-v3) |
| Anthropic SDK | HIGH | Release notes directly verified; v0.96.0 and Opus 4.7 confirmed on GitHub releases |
| Observability (stdlib JSONL) | HIGH | Zero-dep, Logfire compat path exists, ADR-003 schema already fixed |
| Config (Pydantic Settings + YAML) | HIGH | Standard pattern, minimal risk |
| Packaging (uv) | HIGH | Overwhelming 2026 mindshare/speed data; deviation from paul-thinkpiece-pipeline is deliberate (research vs production posture) |
| Openclaw integration | HIGH | Directly read official docs (v2026.4.5) + working wipe-haus-state install; no guesswork |

---

## Sources

### Authoritative / installed
- OpenClaw v2026.4.5 docs at `/home/admin/.npm-global/lib/node_modules/openclaw/docs/` (concepts/agent-workspace.md, automation/cron-jobs.md, index.md)
- Working reference install: `/home/admin/wipe-haus-state/openclaw.json` + `/home/admin/wipe-haus-state/workspaces/*/`
- paul-thinkpiece-pipeline conventions: bash+venv pattern inspected at `/home/admin/paul-thinkpiece-pipeline/train_v6_qwen3_32b.sh` and `/home/admin/finetuning/cu130_env.sh`
- Anthropic SDK releases: [anthropic-sdk-python GitHub releases](https://github.com/anthropics/anthropic-sdk-python/releases) (v0.96.0 confirmed 2026-04-16)

### Verified web sources (MEDIUM → HIGH when cross-referenced)
- [vLLM Releases](https://github.com/vllm-project/vllm/releases) — 0.19+ CUDA 13 Blackwell
- [vLLM OpenAI-Compatible Server](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/)
- [Qwen3 on vLLM recipes](https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html)
- [lancedb PyPI](https://pypi.org/project/lancedb/) — 0.30.2 (2026-03-31)
- [LanceDB vs ChromaDB comparison](https://zilliz.com/comparison/chroma-vs-lancedb)
- [Vector DB Comparison 2026 — 4xxi](https://4xxi.com/articles/vector-database-comparison/)
- [Best Embedding Models for RAG 2026 — Milvus](https://milvus.io/blog/choose-embedding-model-rag-2026.md)
- [BGE-M3 benchmark 2026 — Cheney Zhang](https://zc277584121.github.io/rag/2026/03/20/embedding-models-benchmark-2026.html)
- [Anthropic Prompt Caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Anthropic Structured Outputs docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Pydantic Settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [uv vs poetry vs pdm 2026 — scopir.com, bswen](https://scopir.com/posts/best-python-package-managers-2026/)
- [Python Logging Libraries Comparison — Better Stack](https://betterstack.com/community/guides/logging/best-python-logging-libraries/)
- [Pydantic Logfire](https://pydantic.dev/logfire)

### Known gaps / flagged for phase-specific follow-up
- BGE-M3 retrieval quality on Nahuatl names + metaphysics-rule-cards corpus — measure during RAG-01 phase, compare against jina-embeddings-v3 as first ablation
- FP8/NVFP4 quant of Qwen3-32B voice FT on Blackwell — verify quality preservation at merge time; check vs bf16 baseline as part of DRAFTER-01 phase acceptance
- Anthropic workspace-scoped caching interaction with openclaw's agent-per-workspace model — confirm a single workspace/API-key scope covers all critic/extractor/retro calls cleanly; if not, plan explicit cache-key discipline
