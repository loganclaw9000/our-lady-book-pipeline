---
layout: default
title: Pipeline architecture
---

# Pipeline architecture

End-to-end flow for one scene generation, plus the chapter DAG that runs after each chapter ships.

## Component map

```mermaid
flowchart TB
  subgraph corpus["Lore corpus (read-only)"]
    direction TB
    BRIEF[brief.md<br/>premise + POVs]
    ENG[engineering.md<br/>Reliquary + Engine specs]
    REL[relics.md<br/>Spanish saint catalog]
    PAN[pantheon.md<br/>Mexica deity engines]
    SEC[secondary-characters.md]
    OUT[outline.md<br/>27 chapters / 9 blocks]
    KNL[known-liberties.md<br/>anachronism budget]
    GLO[glossary.md]
    MAP[maps.md]
  end

  subgraph ingest["Corpus ingestion (one-shot or on-mtime-change)"]
    direction TB
    CI[CorpusIngester]
    HC[heading_classifier<br/>brief → historical OR metaphysics]
    EMB[BgeM3Embedder<br/>BAAI/bge-m3 1024d]
    ROUTER[router.py<br/>file → axis]
  end

  subgraph indexes["LanceDB indexes (5 typed RAG axes)"]
    direction TB
    HIST[historical.lance<br/>brief+glossary+maps<br/>45 rows]
    META[metaphysics.lance<br/>engineering+relics+brief<br/>51 rows]
    ENT[entity_state.lance<br/>pantheon+secondary+chapter_NN_entities.json<br/>54+ rows]
    ARC[arc_position.lance<br/>outline beat-IDs<br/>27 rows]
    NEG[negative_constraint.lance<br/>known-liberties<br/>45 rows]
  end

  subgraph scene_input["Scene input"]
    STUB[scenes/chNN/chNN_scNN.yaml<br/>POV, date, location, beat function]
  end

  subgraph rag_layer["RAG layer (per scene)"]
    direction TB
    RET_H[HistoricalRetriever]
    RET_M[MetaphysicsRetriever]
    RET_E[EntityStateRetriever]
    RET_A[ArcPositionRetriever]
    RET_N[NegativeConstraintRetriever]
    RERANK[BgeReranker<br/>50→8]
    BUNDLER[ContextPackBundlerImpl<br/>40KB cap<br/>round-robin]
  end

  subgraph voice["Voice serving (vLLM, port 8003)"]
    LORA[paul-voice V6<br/>Qwen3.5-27B + LoRA<br/>bnb 4-bit]
    VLLM[vLLM 0.17 OpenAI server]
  end

  subgraph generate["Generation pipeline (kernel)"]
    direction TB
    SSM[SceneStateMachine]
    MA[ModeADrafter<br/>local voice]
    PP1[postprocess v1.0.0<br/>strip em-dash + mojibake + think]
    CRITIC[SceneCritic<br/>Opus 4.7 via claude-code CLI]
    REGEN[SceneLocalRegenerator<br/>Opus 4.7 via claude-code CLI]
    MB[ModeBDrafter<br/>frontier escape]
    OSC[OscillationDetector]
    ALERT[TelegramAlerter]
  end

  subgraph chapter_dag["Chapter DAG (post-3-scenes)"]
    direction LR
    CONCAT[ConcatAssembler<br/>scenes → canon/chapter_NN.md]
    CRITIC_CH[ChapterCritic]
    EXTRACT[EntityExtractor<br/>Opus → chapter_NN_entities.json]
    REIDX[reindex_entity_state]
    RETRO[RetrospectiveWriter<br/>Opus → retrospectives/chapter_NN.md]
    READER[render_reader.sh<br/>copy → docs/]
  end

  subgraph obs["Observability"]
    JSONL[runs/events.jsonl<br/>stdlib logging]
    PIPELINE[.planning/pipeline_state.json]
    HEARTBEAT[Forge dead-drop<br/>_coordination/]
  end

  BRIEF & GLO & MAP --> ROUTER
  ENG & REL --> ROUTER
  PAN & SEC --> ROUTER
  OUT --> ROUTER
  KNL --> ROUTER

  ROUTER --> CI
  HC --> CI
  EMB --> CI
  CI --> HIST
  CI --> META
  CI --> ENT
  CI --> ARC
  CI --> NEG

  STUB --> SSM
  HIST --> RET_H
  META --> RET_M
  ENT --> RET_E
  ARC --> RET_A
  NEG --> RET_N

  RET_H & RET_M & RET_E & RET_A & RET_N --> RERANK
  RERANK --> BUNDLER

  SSM --> BUNDLER
  BUNDLER -->|context_pack| MA
  LORA --> VLLM
  VLLM --> MA
  MA --> PP1
  PP1 --> CRITIC
  BUNDLER -->|context_pack| CRITIC
  CRITIC -- pass --> SSM
  CRITIC -- fail --> REGEN
  REGEN --> PP1
  REGEN -- exhausted --> MB
  MB --> PP1
  MB -- blocked --> ALERT
  REGEN <--> OSC

  SSM -->|3 scenes pass| CONCAT
  CONCAT --> CRITIC_CH
  CRITIC_CH --> EXTRACT
  EXTRACT --> REIDX
  REIDX -.merges into.-> ENT
  EXTRACT --> RETRO
  CONCAT --> READER

  MA & CRITIC & REGEN & MB & CONCAT & CRITIC_CH & EXTRACT & RETRO --> JSONL
  SSM --> PIPELINE
  PIPELINE -.coord.-> HEARTBEAT
```

## Stage-by-stage data contracts

| Stage | Input | Output | Backend |
|---|---|---|---|
| **Ingest** | 9 lore .md files | 5 LanceDB tables (217 rows total) | BGE-M3 local |
| **Retrievers** | SceneRequest | 5 axis-typed RetrievalHit lists | LanceDB ANN + filter |
| **Reranker** | candidate_k=50 | final_k=8 | BAAI/bge-reranker-v2-m3 |
| **Bundler** | 5 hit lists | ContextPack (≤40KB, round-robin) | pure Python |
| **ModeADrafter** | ContextPack + scene stub | scene_text (~600-800 words) | vLLM paul-voice |
| **postprocess** | raw scene_text | cleaned scene_text | Forge v1.0.0 contract |
| **SceneCritic** | scene_text + ContextPack + rubric | per-axis scores + overall pass | Opus 4.7 (CLI) |
| **SceneLocalRegenerator** | failed scene + critic feedback + ContextPack | regenerated scene_text | Opus 4.7 (CLI) |
| **ModeBDrafter** | ContextPack | new scene_text | Opus 4.7 (CLI) |
| **ChapterCritic** | concatenated scenes | per-axis chapter scores | Opus 4.7 (CLI) |
| **EntityExtractor** | concatenated chapter | EntityCard JSON | Opus 4.7 (CLI) |
| **reindex_entity_state** | chapter_NN_entities.json | entity_state.lance rows | BGE-M3 local |
| **RetrospectiveWriter** | scene buffer + critic logs + entities | retrospective markdown | Opus 4.7 (CLI) |

## Critical observations

1. **Drafter sees the lore.** The `context_pack` parameter threads through every LLM call. If the pack is empty, the LLM hallucinates; if rich, it's grounded.
2. **The mecha bible lives in `metaphysics.lance`** (engineering.md + relics.md + brief.md sanctified-death sections). 51 rows after 2026-04-24 ingest.
3. **Negative-constraint** carries the explicit "core liberty: mecha" tag. Drafter sees this — anachronism is feature, not bug.
4. **entity_state is a UNION** of static lore (pantheon + secondary characters) and dynamic per-chapter extracted state. The `reindex_entity_state_from_jsons` helper currently wipes-and-rebuilds from per-chapter JSON only — it would nuke pantheon/secondary rows. **OPEN BUG: the helper must filter `source_file` on delete to preserve corpus rows.**
5. **Chapter DAG step 3 calls reindex_entity_state** — runs after each chapter. This means after first DAG, pantheon entities go missing again until re-ingest. See remediation.

## Boundaries (kernel vs CLI vs book-specific)

- **kernel:** corpus_ingest, rag, drafter, critic, regenerator, chapter_assembler, retrospective, entity_extractor, voice_fidelity, observability, llm_clients, alerts, ablation
- **book_specifics:** corpus_paths, heading_classifier, voice_samples, training_corpus, anchor_sources, outline_scene_counts, nahuatl_entities, vllm_endpoints
- **CLI composition root:** cli/draft.py, cli/chapter.py, cli/ingest.py — only modules permitted to import book_specifics

import-linter contracts 1+2 enforce the boundary.
