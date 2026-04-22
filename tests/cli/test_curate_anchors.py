"""Tests for book-pipeline curate-anchors CLI (Plan 03-02 Task 2).

The CLI:
  1. Loads ANCHOR_CANDIDATES (book-domain pointers) from book_specifics.
  2. Iterates source rows, classifies sub-genre, applies quotas.
  3. Builds AnchorSet, computes SHA.
  4. Writes config/voice_anchors/anchor_set_v1.yaml atomically.
  5. If --skip-embed not set: computes centroid + writes embeddings.parquet.
  6. Updates config/mode_thresholds.yaml voice_fidelity.anchor_set_sha.
  7. Emits one role='anchor_curator' Event.

Tests cover: small fixture round-trip (test 1), default-quota production-shape
(1b, W-5), quota-short abort (1c, W-3/W-5), missing blog-heldout tolerance
(test 2), embeddings parquet shape (test 3 — requires fake embedder), YAML
determinism (test 4), threshold validator (test 5), anchor_set_sha pinned
(test 6).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

# --- Fixtures + helpers --------------------------------------------------


def _write_thinkpiece_fixture(
    jsonl_path: Path,
    *,
    essay_count: int = 10,
    analytic_count: int = 10,
    narrative_count: int = 8,
) -> None:
    """Synthesize a jsonl corpus shaped like train_filtered.jsonl.

    Each row: {"conversations": [{"from":"system",...},{"from":"human",...},
    {"from":"gpt","value":<text>}]}. The gpt turn's value is the anchor
    candidate. Each text is 200+ words so it passes the 150-400 filter.

    Sub-genre keywords per _classify_sub_genre heuristic:
      essay — contains "writing"
      analytic — contains "dataset"
      narrative — contains dialogue quote + "she walked"
    """
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    def body_neutral(idx: int) -> str:
        # ~200 words, em-dash + numeric specificity, no classifier-keyword
        # markers so the row_text doesn't fight the prefix's sub-genre tag.
        # (Classifier keywords to avoid: writing/craft/reading/what-i/why-i/how-i
        # for essay; dataset/benchmark/token/model/evaluation/score/metric/data/
        # analysis/system/measure/pattern/signal/framework/tradeoff/
        # infrastructure/protocol/api/algorithm for analytic; dialogue-quote +
        # she/he-said/walked/turned/looked for narrative.)
        return (
            f"Thought {idx} — the moment the screen blinked to life "
            f"at 3:47 AM was something I had imagined 47 times but never "
            f"quite like this. What surprised me was not the hardware but "
            f"the quiet way the room changed around it. The test was "
            f"simple: would the 128 examples I had curated by hand "
            "actually produce something coherent? They did, mostly, "
            "and then they did not, and then it repeated in ways that "
            "felt like a small revelation — not the kind you announce "
            "but the kind you mention in passing to a friend a week "
            "later, wondering if it holds up. The answer: it mostly "
            "does, but in a narrower band than I had expected. Still, "
            "there is something to say here about how the numbers "
            "change the way you think about the thing you are actually "
            "doing, which matters more than it seems at 3:47 AM on a "
            "Tuesday when the only company is the fan's steady hum."
        )

    rows = []
    for i in range(essay_count):
        text = f"I care about writing and craft — {body_neutral(i)}"
        rows.append(_mk_conv_row(text))
    for i in range(analytic_count):
        text = f"The dataset contained 10751 rows — {body_neutral(i)}"
        rows.append(_mk_conv_row(text))
    for i in range(narrative_count):
        text = (
            f'"This is it," she said. She walked to the edge. '
            f'He turned and looked at her — {body_neutral(i)}'
        )
        rows.append(_mk_conv_row(text))

    with jsonl_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _mk_conv_row(gpt_value: str) -> dict:
    return {
        "conversations": [
            {"from": "system", "value": "You are Paul Logan."},
            {"from": "human", "value": "Write something."},
            {"from": "gpt", "value": gpt_value},
        ]
    }


def _install_stub_embedder_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch book_pipeline.rag to expose a fake BgeM3Embedder.

    The real BgeM3Embedder downloads a 2GB model on first use — far too
    heavy for unit tests. We replace it with a deterministic seeded stub.
    """
    import book_pipeline.rag as _rag

    class StubEmbedder:
        revision_sha: str = "stub-bge-m3-rev-abcdef"

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def embed_texts(self, texts: list[str]) -> np.ndarray:
            out = np.zeros((len(texts), 1024), dtype=np.float32)
            for i, t in enumerate(texts):
                seed = hash(t) & 0xFFFF_FFFF
                rng = np.random.default_rng(seed=seed)
                out[i] = rng.standard_normal(1024).astype(np.float32)
            return out

    monkeypatch.setattr(_rag, "BgeM3Embedder", StubEmbedder)


def _seed_mode_thresholds_yaml(yaml_path: Path) -> None:
    """Copy the canonical mode_thresholds shape into a tmp-path copy so
    pydantic loads succeed before curate-anchors rewrites it."""
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "mode_a": {
            "regen_budget_R": 3,
            "per_scene_cost_cap_usd": 0.0,
            "voice_fidelity_band": {"min": 0.60, "max": 0.88},
        },
        "mode_b": {
            "model_id": "claude-opus-4-7",
            "per_scene_cost_cap_usd": 2.00,
            "regen_attempts": 1,
            "prompt_cache_ttl": "1h",
        },
        "oscillation": {"enabled": True, "max_axis_flips": 2},
        "alerts": {
            "telegram_cool_down_seconds": 3600,
            "dedup_window_seconds": 3600,
        },
        "preflag_beats": [],
        "voice_fidelity": {
            "anchor_set_sha": "TBD-curate-anchors-run",
            "pass_threshold": 0.78,
            "flag_band_min": 0.75,
            "flag_band_max": 0.78,
            "fail_threshold": 0.75,
            "memorization_flag_threshold": 0.95,
        },
    }
    yaml_path.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")


def _run_curate_anchors(args: list[str]) -> int:
    from book_pipeline.cli.main import main

    return main(["curate-anchors", *args])


# --- Test 1: small fixture round-trip -----------------------------------


def test_curate_anchors_small_fixture_roundtrips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 1: --skip-embed with --override-quotas essay=3,analytic=3,narrative=3
    against a 3e+3a+3n fixture produces a valid 9-anchor anchor_set_v1.yaml."""
    corpus = tmp_path / "thinkpiece" / "train_filtered.jsonl"
    _write_thinkpiece_fixture(
        corpus, essay_count=3, analytic_count=3, narrative_count=3
    )

    yaml_path = tmp_path / "config" / "voice_anchors" / "anchor_set_v1.yaml"
    thresholds_path = tmp_path / "config" / "mode_thresholds.yaml"
    _seed_mode_thresholds_yaml(thresholds_path)
    events_path = tmp_path / "runs" / "events.jsonl"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OBS_CURATE_ANCHORS_THINKPIECE_PATH", str(corpus))
    monkeypatch.setenv("OBS_CURATE_ANCHORS_BLOG_PATH", str(tmp_path / "missing_blog.jsonl"))

    rc = _run_curate_anchors([
        "--yaml-path", str(yaml_path),
        "--thresholds-path", str(thresholds_path),
        "--events-path", str(events_path),
        "--skip-embed",
        "--override-quotas", "essay=3,analytic=3,narrative=3",
    ])
    assert rc == 0, "curate-anchors small fixture must exit 0"

    # Reload via AnchorSet to check validity.
    from book_pipeline.voice_fidelity.anchors import AnchorSet

    loaded = AnchorSet.load_from_yaml(yaml_path)
    assert len(loaded.anchors) == 9
    sub_genres = [a.sub_genre for a in loaded.anchors]
    assert sub_genres.count("essay") == 3
    assert sub_genres.count("analytic") == 3
    assert sub_genres.count("narrative") == 3


# --- Test 1b (W-5): default quota against sufficient-rows corpus --------


def test_curate_anchors_default_quotas_with_sufficient_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 1b: DEFAULT quotas (8/8/6) against a corpus with 10/10/8 rows
    yields exactly 22 anchors with the expected sub-genre distribution."""
    corpus = tmp_path / "thinkpiece" / "train_filtered.jsonl"
    _write_thinkpiece_fixture(
        corpus, essay_count=10, analytic_count=10, narrative_count=8
    )

    yaml_path = tmp_path / "config" / "voice_anchors" / "anchor_set_v1.yaml"
    thresholds_path = tmp_path / "config" / "mode_thresholds.yaml"
    _seed_mode_thresholds_yaml(thresholds_path)
    events_path = tmp_path / "runs" / "events.jsonl"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OBS_CURATE_ANCHORS_THINKPIECE_PATH", str(corpus))
    monkeypatch.setenv("OBS_CURATE_ANCHORS_BLOG_PATH", str(tmp_path / "missing_blog.jsonl"))

    rc = _run_curate_anchors([
        "--yaml-path", str(yaml_path),
        "--thresholds-path", str(thresholds_path),
        "--events-path", str(events_path),
        "--skip-embed",
    ])
    assert rc == 0, "default-quota curate must exit 0 when corpus is sufficient"

    from book_pipeline.voice_fidelity.anchors import AnchorSet

    loaded = AnchorSet.load_from_yaml(yaml_path)
    assert len(loaded.anchors) == 22
    sub_genres = [a.sub_genre for a in loaded.anchors]
    assert sub_genres.count("essay") == 8
    assert sub_genres.count("analytic") == 8
    assert sub_genres.count("narrative") == 6


# --- Test 1c (W-3/W-5): quota-short abort -------------------------------


def test_curate_anchors_quota_short_aborts_with_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test 1c: Corpus with only 4 essay rows + default 8/8/6 quotas → exit 3,
    stderr names all three sub-genres with need/have/SHORT-or-ok + mentions
    both --override-quotas and 'widen the source' remediation paths."""
    corpus = tmp_path / "thinkpiece" / "train_filtered.jsonl"
    _write_thinkpiece_fixture(
        corpus, essay_count=4, analytic_count=0, narrative_count=0
    )

    yaml_path = tmp_path / "config" / "voice_anchors" / "anchor_set_v1.yaml"
    thresholds_path = tmp_path / "config" / "mode_thresholds.yaml"
    _seed_mode_thresholds_yaml(thresholds_path)
    events_path = tmp_path / "runs" / "events.jsonl"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OBS_CURATE_ANCHORS_THINKPIECE_PATH", str(corpus))
    monkeypatch.setenv("OBS_CURATE_ANCHORS_BLOG_PATH", str(tmp_path / "missing_blog.jsonl"))

    rc = _run_curate_anchors([
        "--yaml-path", str(yaml_path),
        "--thresholds-path", str(thresholds_path),
        "--events-path", str(events_path),
        "--skip-embed",
    ])
    assert rc == 3, "quota-short default quotas must exit 3"

    captured = capsys.readouterr()
    err = captured.err
    assert "QUOTA CHECK FAILED" in err
    assert "essay" in err and "analytic" in err and "narrative" in err
    assert "SHORT" in err
    assert "--override-quotas" in err
    assert "widen the source" in err or "widen" in err

    # Pre-existing yaml untouched (file not written on abort).
    assert not yaml_path.exists(), "yaml must NOT be written on abort"


# --- Test 2: missing blog-heldout tolerated -----------------------------


def test_curate_anchors_tolerates_missing_blog_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 2: blog-heldout path missing → warn + continue with training-only
    rows. (The default _write_thinkpiece_fixture already exercises this —
    we just confirm no crash + the anchors land.)"""
    corpus = tmp_path / "thinkpiece" / "train_filtered.jsonl"
    _write_thinkpiece_fixture(
        corpus, essay_count=3, analytic_count=3, narrative_count=3
    )

    yaml_path = tmp_path / "config" / "voice_anchors" / "anchor_set_v1.yaml"
    thresholds_path = tmp_path / "config" / "mode_thresholds.yaml"
    _seed_mode_thresholds_yaml(thresholds_path)
    events_path = tmp_path / "runs" / "events.jsonl"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OBS_CURATE_ANCHORS_THINKPIECE_PATH", str(corpus))
    # Point blog path at a non-existent file. CLI must NOT crash.
    monkeypatch.setenv(
        "OBS_CURATE_ANCHORS_BLOG_PATH", str(tmp_path / "blog_definitely_missing.jsonl")
    )

    rc = _run_curate_anchors([
        "--yaml-path", str(yaml_path),
        "--thresholds-path", str(thresholds_path),
        "--events-path", str(events_path),
        "--skip-embed",
        "--override-quotas", "essay=3,analytic=3,narrative=3",
    ])
    assert rc == 0


# --- Test 3: embeddings parquet shape -----------------------------------


def test_curate_anchors_writes_embeddings_parquet_when_not_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 3: Without --skip-embed, embeddings.parquet is written with
    shape (N, 1024) float32 (using a stub embedder)."""
    corpus = tmp_path / "thinkpiece" / "train_filtered.jsonl"
    _write_thinkpiece_fixture(
        corpus, essay_count=3, analytic_count=3, narrative_count=3
    )

    yaml_path = tmp_path / "config" / "voice_anchors" / "anchor_set_v1.yaml"
    thresholds_path = tmp_path / "config" / "mode_thresholds.yaml"
    _seed_mode_thresholds_yaml(thresholds_path)
    embeddings_path = tmp_path / "indexes" / "voice_anchors" / "embeddings.parquet"
    events_path = tmp_path / "runs" / "events.jsonl"

    _install_stub_embedder_module(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OBS_CURATE_ANCHORS_THINKPIECE_PATH", str(corpus))
    monkeypatch.setenv("OBS_CURATE_ANCHORS_BLOG_PATH", str(tmp_path / "missing_blog.jsonl"))

    rc = _run_curate_anchors([
        "--yaml-path", str(yaml_path),
        "--thresholds-path", str(thresholds_path),
        "--embeddings-path", str(embeddings_path),
        "--events-path", str(events_path),
        "--override-quotas", "essay=3,analytic=3,narrative=3",
    ])
    assert rc == 0
    assert embeddings_path.exists()

    import pyarrow.parquet as pq

    table = pq.read_table(embeddings_path)
    assert table.num_rows == 9
    # id + sub_genre + embedding columns expected.
    assert {"id", "sub_genre", "embedding"}.issubset(set(table.column_names))


# --- Test 4: deterministic yaml output ----------------------------------


def test_curate_anchors_deterministic_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 4: running curate-anchors twice against the same fixture produces
    byte-identical yaml output."""
    corpus = tmp_path / "thinkpiece" / "train_filtered.jsonl"
    _write_thinkpiece_fixture(
        corpus, essay_count=3, analytic_count=3, narrative_count=3
    )

    yaml1 = tmp_path / "run1" / "anchor_set_v1.yaml"
    yaml2 = tmp_path / "run2" / "anchor_set_v1.yaml"
    thresholds1 = tmp_path / "run1" / "mode_thresholds.yaml"
    thresholds2 = tmp_path / "run2" / "mode_thresholds.yaml"
    _seed_mode_thresholds_yaml(thresholds1)
    _seed_mode_thresholds_yaml(thresholds2)
    events1 = tmp_path / "run1" / "events.jsonl"
    events2 = tmp_path / "run2" / "events.jsonl"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OBS_CURATE_ANCHORS_THINKPIECE_PATH", str(corpus))
    monkeypatch.setenv("OBS_CURATE_ANCHORS_BLOG_PATH", str(tmp_path / "missing.jsonl"))

    for yp, thp, evp in [(yaml1, thresholds1, events1), (yaml2, thresholds2, events2)]:
        rc = _run_curate_anchors([
            "--yaml-path", str(yp),
            "--thresholds-path", str(thp),
            "--events-path", str(evp),
            "--skip-embed",
            "--override-quotas", "essay=3,analytic=3,narrative=3",
        ])
        assert rc == 0

    assert yaml1.read_bytes() == yaml2.read_bytes(), "yaml must be byte-identical across runs"


# --- Test 5: VoiceFidelityConfig validator (threshold interval) ---------


def test_voice_fidelity_config_rejects_inconsistent_thresholds() -> None:
    """Test 5: VoiceFidelityConfig validator rejects pass_threshold >=
    memorization_flag_threshold (misconfigured interval)."""
    from pydantic import ValidationError

    from book_pipeline.config.mode_thresholds import VoiceFidelityConfig

    # Valid config (pins in plan 03-02).
    ok = VoiceFidelityConfig(
        anchor_set_sha="a" * 64,
        pass_threshold=0.78,
        flag_band_min=0.75,
        flag_band_max=0.78,
        fail_threshold=0.75,
        memorization_flag_threshold=0.95,
    )
    assert ok.pass_threshold < ok.memorization_flag_threshold

    # Invalid: pass_threshold >= memorization_flag_threshold.
    with pytest.raises(ValidationError):
        VoiceFidelityConfig(
            anchor_set_sha="a" * 64,
            pass_threshold=0.96,
            flag_band_min=0.75,
            flag_band_max=0.78,
            fail_threshold=0.75,
            memorization_flag_threshold=0.95,
        )


# --- Test 6: anchor_set_sha written to mode_thresholds.yaml --------------


def test_curate_anchors_writes_anchor_set_sha_to_thresholds_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 6: post-curation, mode_thresholds.yaml voice_fidelity.anchor_set_sha
    matches AnchorSet.sha byte-for-byte."""
    corpus = tmp_path / "thinkpiece" / "train_filtered.jsonl"
    _write_thinkpiece_fixture(
        corpus, essay_count=3, analytic_count=3, narrative_count=3
    )

    yaml_path = tmp_path / "config" / "voice_anchors" / "anchor_set_v1.yaml"
    thresholds_path = tmp_path / "config" / "mode_thresholds.yaml"
    _seed_mode_thresholds_yaml(thresholds_path)
    events_path = tmp_path / "runs" / "events.jsonl"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OBS_CURATE_ANCHORS_THINKPIECE_PATH", str(corpus))
    monkeypatch.setenv("OBS_CURATE_ANCHORS_BLOG_PATH", str(tmp_path / "missing.jsonl"))

    rc = _run_curate_anchors([
        "--yaml-path", str(yaml_path),
        "--thresholds-path", str(thresholds_path),
        "--events-path", str(events_path),
        "--skip-embed",
        "--override-quotas", "essay=3,analytic=3,narrative=3",
    ])
    assert rc == 0

    from book_pipeline.voice_fidelity.anchors import AnchorSet

    loaded = AnchorSet.load_from_yaml(yaml_path)
    thresholds = yaml.safe_load(thresholds_path.read_text(encoding="utf-8"))
    assert thresholds["voice_fidelity"]["anchor_set_sha"] == loaded.sha
    assert len(thresholds["voice_fidelity"]["anchor_set_sha"]) == 64
    assert thresholds["voice_fidelity"]["pass_threshold"] == 0.78
    assert thresholds["voice_fidelity"]["memorization_flag_threshold"] == 0.95


# --- Test 7: anchor_curator Event emitted -------------------------------


def test_curate_anchors_emits_anchor_curator_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 7: exactly one role='anchor_curator' Event lands in events.jsonl
    with sub_genre_counts + anchor_set_sha."""
    corpus = tmp_path / "thinkpiece" / "train_filtered.jsonl"
    _write_thinkpiece_fixture(
        corpus, essay_count=3, analytic_count=3, narrative_count=3
    )

    yaml_path = tmp_path / "config" / "voice_anchors" / "anchor_set_v1.yaml"
    thresholds_path = tmp_path / "config" / "mode_thresholds.yaml"
    _seed_mode_thresholds_yaml(thresholds_path)
    events_path = tmp_path / "runs" / "events.jsonl"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OBS_CURATE_ANCHORS_THINKPIECE_PATH", str(corpus))
    monkeypatch.setenv("OBS_CURATE_ANCHORS_BLOG_PATH", str(tmp_path / "missing.jsonl"))

    rc = _run_curate_anchors([
        "--yaml-path", str(yaml_path),
        "--thresholds-path", str(thresholds_path),
        "--events-path", str(events_path),
        "--skip-embed",
        "--override-quotas", "essay=3,analytic=3,narrative=3",
    ])
    assert rc == 0

    assert events_path.exists()
    lines = [ln for ln in events_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    curator_events = [json.loads(ln) for ln in lines if '"anchor_curator"' in ln]
    assert len(curator_events) == 1, f"expected 1 anchor_curator event, got {len(curator_events)}"
    ev = curator_events[0]
    assert ev["role"] == "anchor_curator"
    assert ev["caller_context"]["module"] == "cli.curate_anchors"
    assert "sub_genre_counts" in ev["caller_context"]
    sub_counts = ev["caller_context"]["sub_genre_counts"]
    assert sub_counts == {"essay": 3, "analytic": 3, "narrative": 3}
    # output_hash == anchor_set_sha
    from book_pipeline.voice_fidelity.anchors import AnchorSet

    loaded = AnchorSet.load_from_yaml(yaml_path)
    assert ev["output_hash"] == loaded.sha


# --- Test 8: classify_sub_genre heuristic -------------------------------


def test_classify_sub_genre_keywords() -> None:
    """Test 8 (Task 2 book_specifics unit): _classify_sub_genre returns
    correct label for each sub-genre's keyword markers."""
    from book_pipeline.book_specifics.anchor_sources import _classify_sub_genre

    assert _classify_sub_genre(
        "I care about writing and craft. This is about how I work."
    ) == "essay"
    assert _classify_sub_genre(
        "The dataset had 10751 rows across 5 benchmark tasks."
    ) == "analytic"
    assert _classify_sub_genre(
        '"Stay," she said. He walked to the window and turned. "Not tonight."'
    ) == "narrative"
