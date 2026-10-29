"""Generate pinned DeerFlow configuration without writing literal model keys."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from .config import ConfigurationError, ModelSpec

DEERFLOW_COMMIT = "e9074b7126833b5ca4739bcedcbbed01b211246c"


def build_config(
    model: ModelSpec,
    *,
    tools: Sequence[dict[str, str]] = (),
    authorization_provider: str | None = None,
    prompt: str = "",
) -> dict:
    if tools and not authorization_provider:
        raise ConfigurationError("Tools require an authorization_provider")
    entry: dict = {
        "name": "primary",
        "use": "langchain_ollama:ChatOllama" if model.provider == "ollama" else "langchain_openai:ChatOpenAI",
        "model": model.model,
        "base_url": model.base_url.removesuffix("/v1") if model.provider == "ollama" else model.base_url,
        "temperature": model.temperature,
        "max_tokens": 4096,
        "supports_thinking": False,
        "supports_vision": model.supports_vision,
    }
    if model.provider == "openai":
        entry.update(api_key="$AGENT_RUNTIME_MODEL_KEY", timeout=45, max_retries=0)
        if model.disable_thinking:
            entry["extra_body"] = {"thinking": {"type": "disabled"}}
    groups = [{"name": "application"}] if tools else []
    config = {
        "config_version": 62,
        "models": [entry],
        "database": {"backend": "memory"},
        "tool_groups": groups,
        "tools": list(tools),
        "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider", "allow_host_bash": False},
        "authorization": {
            "enabled": bool(tools),
            "fail_closed": True,
            **({"provider": {"use": authorization_provider}} if authorization_provider else {}),
        },
        "memory": {"enabled": False},
        "summarization": {"enabled": False},
        "subagents": {"enabled": False},
        "task_continuity": {"enabled": False},
        "title": {"enabled": False},
        "lead_prompt_overlay": {"prepend": prompt},
    }
    return config


def write_config(config: dict, data_dir: Path) -> Path:
    """Create a private, replaceable config file in the persistent runtime directory."""
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    data_dir.chmod(0o700)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=data_dir, prefix="deerflow-", suffix=".yaml", delete=False) as file:
        yaml.safe_dump(config, file, allow_unicode=True, sort_keys=False)
        path = Path(file.name)
    path.chmod(0o600)
    return path


def set_runtime_environment(model: ModelSpec, env: Mapping[str, str] | None = None, *, data_dir: Path) -> None:
    env = os.environ if env is None else env
    os.environ["AGENT_RUNTIME_MODEL_KEY"] = model.secret(env)
    os.environ["DEER_FLOW_HOME"] = str(data_dir / "deerflow-home")
    os.environ["DEER_FLOW_PROJECT_ROOT"] = str(Path.cwd())
    os.environ["DEER_FLOW_DATE_TIMEZONE"] = env.get("DEER_FLOW_DATE_TIMEZONE", "Asia/Shanghai")
