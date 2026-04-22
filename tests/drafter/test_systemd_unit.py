"""Tests for book_pipeline.drafter.systemd_unit (Plan 03-03 Task 2).

render_unit / write_unit / systemctl_user / daemon_reload / poll_health.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest


def _minimal_kwargs() -> dict[str, object]:
    return {
        "base_model": "Qwen/Qwen3-32B",
        "adapter_path": "/home/admin/finetuning/output/paul-v6-qwen3-32b-lora",
        "port": 8002,
        "dtype": "bfloat16",
        "max_model_len": 8192,
        "tensor_parallel_size": 1,
        "gpu_memory_utilization": 0.85,
        "venv_python": "/home/admin/finetuning/venv_cu130/bin/python",
        "environment_file": "/home/admin/finetuning/cu130.env",
        "ft_run_id": "v6_qwen3_32b",
    }


def test_render_unit_produces_expected_flags(tmp_path: Path) -> None:
    """Test 1: render_unit contains --model, --enable-lora, --lora-modules paul-voice=, --port 8002."""
    from book_pipeline.drafter.systemd_unit import render_unit

    template_path = Path("config/systemd/vllm-paul-voice.service.j2")
    out = render_unit(template_path, **_minimal_kwargs())
    assert "--model Qwen/Qwen3-32B" in out
    assert "--enable-lora" in out
    assert (
        "--lora-modules paul-voice=/home/admin/finetuning/output/paul-v6-qwen3-32b-lora"
        in out
    )
    assert "--port 8002" in out
    assert "--dtype bfloat16" in out
    assert "--max-model-len 8192" in out
    assert "--gpu-memory-utilization 0.85" in out
    assert "/home/admin/finetuning/venv_cu130/bin/python" in out


def test_render_unit_missing_var_raises_keyerror(tmp_path: Path) -> None:
    """Test 2: StrictUndefined missing var → KeyError naming the variable."""
    from book_pipeline.drafter.systemd_unit import render_unit

    template_path = Path("config/systemd/vllm-paul-voice.service.j2")
    kwargs = _minimal_kwargs()
    del kwargs["port"]  # deliberately drop a required var
    with pytest.raises(KeyError) as excinfo:
        render_unit(template_path, **kwargs)
    assert "port" in str(excinfo.value)


def test_write_unit_is_atomic(tmp_path: Path) -> None:
    """Test 3: write_unit uses tmp+rename; tmp file does not exist after success."""
    from book_pipeline.drafter.systemd_unit import write_unit

    unit_dir = tmp_path / "systemd"
    content = "[Unit]\nDescription=test\n"
    final = write_unit(unit_dir, "vllm-paul-voice.service", content)
    assert final.exists()
    assert final.read_text(encoding="utf-8") == content
    tmp = unit_dir / "vllm-paul-voice.service.tmp"
    assert not tmp.exists(), "atomic-write tmp should be gone after os.replace"


def test_poll_health_returns_true_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 7a: poll_health returns True quickly when vLLM answers 200."""
    from book_pipeline.drafter import systemd_unit as su

    def fake_get(url: str, timeout: float) -> httpx.Response:  # type: ignore[override]
        return httpx.Response(200, json={"data": []})

    monkeypatch.setattr(su, "_probe_models", fake_get)
    ok = su.poll_health("http://test/v1", timeout_s=5.0, interval_s=0.1)
    assert ok is True


def test_poll_health_returns_false_on_persistent_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 7b: poll_health returns False after timeout if all probes raise."""
    from book_pipeline.drafter import systemd_unit as su

    def fake_get(url: str, timeout: float) -> httpx.Response:  # type: ignore[override]
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(su, "_probe_models", fake_get)
    ok = su.poll_health("http://test/v1", timeout_s=0.3, interval_s=0.1)
    assert ok is False


def test_systemctl_user_returns_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    """systemctl_user wraps subprocess.run with check=False, returns (ok, stdout, stderr)."""
    from book_pipeline.drafter import systemd_unit as su

    class _Result:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_run(*a: object, **kw: object) -> _Result:
        return _Result()

    monkeypatch.setattr(su.subprocess, "run", fake_run)
    ok, out, err = su.systemctl_user("start", "vllm-paul-voice.service")
    assert ok is True
    assert out == "ok\n"
    assert err == ""


def test_systemd_unit_is_kernel_clean() -> None:
    """drafter/systemd_unit.py must not import book_specifics."""
    import pathlib

    src = pathlib.Path("src/book_pipeline/drafter/systemd_unit.py").read_text(
        encoding="utf-8"
    )
    assert "book_specifics" not in src
