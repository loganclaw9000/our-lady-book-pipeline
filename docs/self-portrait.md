---
layout: default
title: Self-portrait — pipeline architecture
---

# Self-portrait

How this novel is being written, drawn by the agent that's writing it.

## End-to-end pipeline

<div class="mermaid">
flowchart TB
    subgraph corpus["📚 Lore corpus (read-only)"]
        BIBLE[chapter outlines + character bibles<br/>+ engineering bible + pantheon bible<br/>+ relic bible + glossary]
    end

    subgraph forge["🔥 Forge — paul-thinkpiece-pipeline"]
        TRAIN["train.py (Unsloth + bnb-4bit)<br/>Qwen3.5-27B + LoRA r=16"]
        EVAL["v7d_iterate_eval.py<br/>200-prompt sweep<br/>rewrite_para / continuation /<br/>adversarial gates"]
        MANIFEST["MANIFEST.json + sha256<br/>shards (manifest_digest)"]
        TRAIN --> EVAL
        EVAL --> MANIFEST
    end

    subgraph scribe["✍️ Scribe — our-lady-book-pipeline"]
        PIN["voice_pin.yaml<br/>(V-3 sha verified at boot)"]
        VLLM["vllm-paul-voice systemd unit<br/>(LoRA-on-bnb @ 8003)"]

        subgraph rag["RAG (5+1 axes · BGE-M3 · LanceDB)"]
            RETHIST[historical]
            RETMETA[metaphysics]
            RETENT[entity_state]
            RETARC[arc_position]
            RETNEG[negative_constraint]
            RETCB[continuity_bible<br/>CB-01]
        end

        BUNDLE["ContextPackBundler<br/>(per-axis trim · stale-card detect)"]

        subgraph draft["Drafter (Mode-A)"]
            MODA["mode_a.py → vllm /completions<br/>scene_type sampling profile<br/>postprocess: strip-think + em-dash<br/>+ mojibake + voice fidelity score"]
        end

        subgraph crit["Critic (13-axis · rubric_v2)"]
            PRELLM["pre-LLM short-circuits<br/>(stub_leak · repetition_loop ·<br/>pov_narrative_voice · scene_buffer cosine)"]
            OPUS["Claude Opus 4.7 via claude-code CLI<br/>(structured outputs · 1h prompt cache)"]
            PRELLM --> OPUS
        end

        REGEN["Regenerator<br/>(diversify directive on attempt ≥2 ·<br/>temperature ramp · word-count guard)"]
        ESCALATE["Mode-B escalation<br/>(preflag · oscillation ·<br/>r_cap_exhausted · spend_cap)"]
        MODB["Mode-B Drafter<br/>(Claude Opus 4.7 frontier)"]

        DAG["Chapter DAG (4 atomic commits)<br/>1. assemble + chapter_critic<br/>2. entity_extractor → entity-state/<br/>3. RAG reindex (continuity_bible)<br/>4. retrospective_writer"]

        BUFFER["scene_buffer SQLite<br/>(committed-only embeddings ·<br/>cosine override deterministic)"]

        ALERT["Telegram alerter<br/>(8 hard-block conditions ·<br/>1h cooldown · LRU dedup)"]
        EVENTS["runs/events.jsonl<br/>(every LLM call · idempotent ingest →<br/>SQLite metric ledger)"]
    end

    subgraph reader["🌐 gh-pages reader"]
        SITE["loganclaw9000.github.io/<br/>our-lady-book-pipeline"]
        FORM["per-page anonymous<br/>feedback &lt;form&gt;"]
        WORKER["Cloudflare Worker<br/>(POST → GH Issues label=feedback)"]
        ISSUES["GitHub Issues<br/>label: feedback"]
        DIGEST["scripts/read_feedback.sh<br/>→ .planning/feedback/FEEDBACK.md"]
    end

    subgraph coord["🤝 Coordination (cross-project)"]
        STATE1["scribe_pipeline_state.json"]
        STATE2["voice_pipeline_state.json"]
        CHAN1["novel_to_voice.jsonl"]
        CHAN2["voice_to_novel.jsonl"]
        ADAPTER["TCP-backoff adaptive_tier<br/>(systemd-driven 30s tick ·<br/>T0 / T1 / T2 / T3 cadence)"]
    end

    OPERATOR(("🧑 Operator<br/>review gate ·<br/>weekly digest ·<br/>hard-block alerts"))

    BIBLE -.-> RETHIST & RETMETA & RETENT & RETARC & RETNEG & RETCB
    BIBLE --> TRAIN
    MANIFEST -.->|operator approves| PIN
    PIN --> VLLM
    VLLM --> MODA

    RETHIST & RETMETA & RETENT & RETARC & RETNEG & RETCB --> BUNDLE
    BUNDLE --> MODA
    MODA --> PRELLM
    OPUS --> REGEN
    REGEN --> MODA
    REGEN -.->|spend_cap or r_cap| ESCALATE
    ESCALATE --> MODB
    MODB --> PRELLM
    OPUS -->|pass| DAG
    DAG -->|commit ↑| BUFFER
    DAG -.->|reindex| RETCB
    PRELLM <--> BUFFER

    DAG --> SITE
    SITE --> FORM
    FORM --> WORKER
    WORKER --> ISSUES
    ISSUES --> DIGEST
    DIGEST -.->|next session| BUNDLE

    PIN <-.->|sha verify| MANIFEST
    STATE1 <--> ADAPTER
    STATE2 <--> ADAPTER
    ADAPTER -.-> CHAN1
    ADAPTER -.-> CHAN2
    CHAN1 <--> CHAN2

    EVENTS -.->|hard_block| ALERT
    ALERT -.-> OPERATOR
    OPERATOR -.-> PIN
    OPERATOR -.-> DIGEST

    classDef forgeCls fill:#ffd6a5,stroke:#aa5500
    classDef scribeCls fill:#caffbf,stroke:#1a7a1a
    classDef readerCls fill:#a0c4ff,stroke:#003a99
    classDef coordCls fill:#ffc6ff,stroke:#5a005a
    classDef opCls fill:#fdffb6,stroke:#aaaa00
    class TRAIN,EVAL,MANIFEST forgeCls
    class PIN,VLLM,RETHIST,RETMETA,RETENT,RETARC,RETNEG,RETCB,BUNDLE,MODA,PRELLM,OPUS,REGEN,ESCALATE,MODB,DAG,BUFFER,ALERT,EVENTS scribeCls
    class SITE,FORM,WORKER,ISSUES,DIGEST readerCls
    class STATE1,STATE2,CHAN1,CHAN2,ADAPTER coordCls
    class OPERATOR opCls
</div>

## Per-scene state machine

<div class="mermaid">
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RAG_READY: bundler returns ContextPack
    RAG_READY --> DRAFTED_A: Mode-A drafter
    DRAFTED_A --> CRITIC_PASS: 13-axis critic pass
    DRAFTED_A --> CRITIC_FAIL: any axis FAIL
    CRITIC_FAIL --> REGENERATING: HIGH/MID severity issues
    REGENERATING --> DRAFTED_A: regen text returned
    CRITIC_FAIL --> ESCALATED_B: oscillation /<br/>r_cap_exhausted /<br/>preflag
    ESCALATED_B --> CRITIC_PASS: Mode-B PASS
    ESCALATED_B --> HARD_BLOCKED: Mode-B FAIL or<br/>spend_cap exceeded
    CRITIC_PASS --> COMMITTED: write to drafts/<br/>+ persist embedding
    HARD_BLOCKED --> [*]: alert operator
    COMMITTED --> [*]
</div>

## What each piece does (terse)

| Subsystem | Does what |
|---|---|
| **forge** | trains Qwen3.5-27B LoRA on Paul's prose; ships V7D after gates pass |
| **voice_pin.yaml** | atomic checkpoint pin with V-3 SHA (algo: `sha256(sorted sha256sum manifest)`) |
| **vllm-paul-voice** | serves the LoRA on `127.0.0.1:8003` via systemd unit re-rendered each repin |
| **RAG (5+1 axes)** | each axis is a domain (history / metaphysics / entity / arc / what-not-to-do / continuity-bible); BGE-M3 dense; LanceDB on disk; per-bundle stale-card detection |
| **Mode-A drafter** | local voice-FT first; cheap; voice-faithful but prone to echo |
| **13-axis critic** | 5 original + 6 LLM-judged + 2 pre-LLM short-circuits; Claude Opus 4.7 frontier; structured outputs gate-checked against rubric_v2 |
| **regenerator** | rewrites only flagged passages; word-count guarded; injects diversification directive on attempt ≥2 |
| **Mode-B escalation** | 4 triggers: preflag · oscillation · r_cap exhausted · spend_cap; switches drafter to Claude Opus 4.7 |
| **scene_buffer** | SQLite of committed-scene embeddings; cosine cap for similarity; ONLY writes on commit (PHYSICS-10 fix — used to write attempts, caused self-match) |
| **chapter DAG** | 4 atomic commits per chapter, scene-kick recovery up to 3 cycles before CHAPTER_FAIL |
| **Telegram alerter** | 8 hard-block conditions, 1h cooldown, dedup window |
| **TCP-backoff heartbeat** | scribe + forge exchange JSON heartbeats; tier auto-steps T1↔T2↔T3 on liveness/silence; T0 reserved for explicit conflict mode |
| **Reader feedback** | static HTML form on every page → Cloudflare Worker → labeled GitHub Issue → `scripts/read_feedback.sh` digest into `.planning/feedback/FEEDBACK.md` |

## Coordination protocol

- Heartbeat every 30s tick; tier decides emit (T1=90s, T2=270s, T3=1200s).
- All cross-pipeline messages are JSONL append-only with `correlation_id`.
- Bilateral acks promote a `proposal` into `decisions.jsonl` (canonical contracts).
- Hard-block alerts (incident_log.jsonl) require ack within one heartbeat or both sides drop to safe-mode.

## Source

Repo: [loganclaw9000/our-lady-book-pipeline](https://github.com/loganclaw9000/our-lady-book-pipeline) · sister: [paul-thinkpiece-pipeline](https://github.com/loganclaw9000/paul-thinkpiece-pipeline). Pipelines run on a single DGX Spark GB10 (96 GB unified, sm_121).

{% include mermaid.html %}
