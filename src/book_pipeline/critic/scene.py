"""SceneCritic — CRIT-01 + CRIT-04.

Task 1 lands: SystemPromptBuilder + SceneCriticError skeleton (template render
+ fewshot yaml load + deterministic sha). Task 2 adds the full SceneCritic
class (Anthropic messages.parse + cache_control + tenacity + audit log + Event
emission).

This module lives in the kernel. It MUST NOT carry project-specific logic —
the few-shot YAML is a config asset under templates/, and the rubric is a
project-agnostic 5-axis schema. Import-linter contract 1 (pyproject.toml)
guards the kernel/book-domain boundary on every commit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from book_pipeline.config.rubric import RubricConfig
from book_pipeline.observability.hashing import hash_text

# Canonical 5-axis ordering for the system prompt template. Matches
# REQUIRED_AXES in book_pipeline.config.rubric.
AXES_ORDERED: tuple[str, ...] = ("historical", "metaphysics", "entity", "arc", "donts")


class SceneCriticError(Exception):
    """Raised by SceneCritic on Anthropic failure / shape-violation / invariant break.

    Carries ``reason`` (short tag) + ``context`` (dict of scene_id, attempt,
    underlying cause) so Plan 03-06 scene-loop orchestrator can persist
    HARD_BLOCKED with enough detail for post-mortem.
    """

    def __init__(self, reason: str, **context: Any) -> None:
        self.reason = reason
        self.context = context
        super().__init__(f"SceneCritic: {reason} | {context}")


class SystemPromptBuilder:
    """Renders the critic system prompt from templates/system.j2 + fewshot yaml.

    Pre-rendering the prompt once at SceneCritic.__init__ time means every
    review() call reuses the identical string — Anthropic's prompt cache hits
    on request #2 onward within the 1h TTL window.
    """

    def __init__(
        self,
        rubric: RubricConfig,
        fewshot_path: Path,
        template_path: Path,
    ) -> None:
        self.rubric = rubric
        self.fewshot_path = Path(fewshot_path)
        self.template_path = Path(template_path)

    def _load_fewshot(self) -> dict[str, Any]:
        raw = self.fewshot_path.read_text(encoding="utf-8")
        data: dict[str, Any] = yaml.safe_load(raw)
        return data

    def render(self) -> tuple[str, str]:
        """Return (rendered_system_prompt, system_prompt_sha).

        SHA is ``hash_text(rendered)`` — used as the audit-log
        ``system_prompt_sha`` field and as part of the Event ``prompt_hash``.
        """
        fewshot = self._load_fewshot()
        env = Environment(
            loader=FileSystemLoader(str(self.template_path.parent)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )
        template = env.get_template(self.template_path.name)
        rendered = template.render(
            rubric=self.rubric,
            axes_ordered=list(AXES_ORDERED),
            few_shot_bad=fewshot["bad"],
            few_shot_good=fewshot["good"],
        )
        sha = hash_text(rendered)
        return rendered, sha


__all__ = ["AXES_ORDERED", "SceneCriticError", "SystemPromptBuilder"]
