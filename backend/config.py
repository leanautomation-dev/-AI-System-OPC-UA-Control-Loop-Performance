"""
Centralised configuration loader that supports environment variable
interpolation with bash-style `${VAR:default}` semantics.  Every backend
module should import `load_config` instead of reading `config.yaml` directly.
"""
from __future__ import annotations

import os
import re
from typing import Any

import yaml

_env_pattern = re.compile(r"\$\{([^:}]+)(?::([^}]*))?\}")


def _expand(obj: Any) -> Any:
    if isinstance(obj, str):
        def repl(match: re.Match[str]) -> str:
            var = match.group(1)
            default = match.group(2) or ""
            return os.environ.get(var, default)

        return _env_pattern.sub(repl, obj)
    elif isinstance(obj, dict):
        return {k: _expand(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand(v) for v in obj]
    else:
        return obj


def load_config(path: str = "config.yaml") -> dict[str, Any]:
    """Load the YAML configuration file and expand any ${VAR:default} values.

    Environment variables override defaults; unspecified variables fall back to
    the value after the colon.  Recurses through dicts and lists.
    """
    with open(path) as f:
        cfg = yaml.safe_load(f)
    return _expand(cfg)
