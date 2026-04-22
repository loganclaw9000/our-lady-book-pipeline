"""Shared YAML config source for pydantic-settings v2.

Thin wrapper around ``pydantic_settings.YamlConfigSettingsSource`` that adds
the stricter error semantics FOUND-02 requires:

  - Missing file → FileNotFoundError with the path in the message
    (built-in silently skips missing files; we fail fast).
  - Non-mapping top-level YAML → ValueError.
  - Malformed YAML → yaml.YAMLError propagated from PyYAML.

Subclassing the built-in (rather than reimplementing from
``PydanticBaseSettingsSource``) lets pydantic-settings' internal
``_settings_warn_unused_config_keys`` check recognize us as a YAML source
(it uses ``isinstance``) — so ``yaml_file`` in ``model_config`` doesn't
emit a UserWarning at every instantiation.

The path in ``model_config['yaml_file']`` is resolved relative to the
current working directory, so tests can ``monkeypatch.chdir(tmp_path)`` to
override which YAML is read without mutating ``model_config`` internals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings
from pydantic_settings import YamlConfigSettingsSource as _BuiltinYamlSource


class YamlConfigSettingsSource(_BuiltinYamlSource):
    """Strict YAML source: missing files and non-dict payloads are fatal."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        yaml_file = settings_cls.model_config.get("yaml_file")
        if yaml_file is None:
            return
        path = Path(str(yaml_file))
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {yaml_file}")
        if not isinstance(self.yaml_data, dict):
            raise ValueError(
                f"Config {yaml_file} must deserialize to a mapping, "
                f"got {type(self.yaml_data).__name__}"
            )

    def _read_file(self, file_path: Path) -> dict[str, Any]:
        """Override to surface malformed YAML as yaml.YAMLError (PyYAML default).

        The built-in implementation already does ``yaml.safe_load``; we keep
        that behavior and rely on PyYAML's default error propagation.
        """
        with file_path.open("r", encoding="utf-8") as f:
            loaded: Any = yaml.safe_load(f) or {}
        if not isinstance(loaded, dict):
            # Caught early so callers see a clear message, not a later
            # "expected dict, got str" from pydantic.
            raise ValueError(
                f"Config {file_path} must deserialize to a mapping, got {type(loaded).__name__}"
            )
        return loaded
