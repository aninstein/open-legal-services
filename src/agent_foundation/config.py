"""Strict model and secret references shared by API, worker and deployment."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit


ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str
    base_url: str
    api_key_env: str | None
    temperature: float
    supports_vision: bool
    disable_thinking: bool

    def secret(self, env: Mapping[str, str]) -> str:
        if self.provider == "ollama":
            return "local"
        value = (env.get(self.api_key_env or "") or "").strip()
        if not value:
            raise ConfigurationError(f"{self.model}: missing API key in {self.api_key_env}")
        return value


def _url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigurationError("Model base_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError("Model base_url cannot contain credentials, query or fragment")
    return value.rstrip("/")


def load_models(env: Mapping[str, str] | None = None) -> tuple[ModelSpec, ...]:
    env = os.environ if env is None else env
    try:
        entries = json.loads(env.get("MODEL_CONFIG_JSON", ""))
    except json.JSONDecodeError as exc:
        raise ConfigurationError("MODEL_CONFIG_JSON is invalid JSON") from exc
    if not isinstance(entries, list) or not entries:
        raise ConfigurationError("MODEL_CONFIG_JSON must be a nonempty JSON array")
    models: list[ModelSpec] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ConfigurationError("Every model entry must be an object")
        if entry.get("enabled", True) is False:
            continue
        if "api_key" in entry or "token" in entry:
            raise ConfigurationError("Put credentials in a separate environment variable via api_key_env")
        provider = entry.get("provider", "openai")
        if provider not in {"openai", "ollama"}:
            raise ConfigurationError("provider must be openai or ollama")
        model = entry.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ConfigurationError("Every enabled model needs a model name")
        base_url = _url(str(entry.get("base_url") or ("http://ollama:11434" if provider == "ollama" else "")))
        key_env = entry.get("api_key_env")
        if provider == "openai":
            if not isinstance(key_env, str) or not ENV_NAME.fullmatch(key_env):
                raise ConfigurationError(f"{model}: api_key_env must name an environment variable")
        elif key_env:
            raise ConfigurationError("Ollama entries do not use api_key_env")
        try:
            temperature = float(entry.get("temperature", env.get("MODEL_TEMPERATURE", "0.2")))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("temperature must be a number") from exc
        if not 0 <= temperature <= 2:
            raise ConfigurationError("temperature must be between 0 and 2")
        vision = entry.get("supports_vision", False)
        thinking = entry.get("disable_thinking", False)
        if not isinstance(vision, bool) or not isinstance(thinking, bool):
            raise ConfigurationError("supports_vision and disable_thinking must be booleans")
        models.append(ModelSpec(provider, model.strip(), base_url, key_env, temperature, vision, thinking))
    if not models:
        raise ConfigurationError("No enabled models")
    names = [item.model for item in models]
    if len(names) != len(set(names)):
        raise ConfigurationError("Model IDs must be unique")
    primary = env.get("PRIMARY_MODEL", "").strip()
    if primary:
        if primary not in names:
            raise ConfigurationError("PRIMARY_MODEL must name an enabled model")
        models.sort(key=lambda item: item.model != primary)
    for item in models:
        item.secret(env)
    return tuple(models)


def selected_model(env: Mapping[str, str] | None = None) -> ModelSpec:
    return load_models(env)[0]


def admin_credentials(env: Mapping[str, str] | None = None) -> tuple[str, str]:
    env = os.environ if env is None else env
    username = env.get("APP_ADMIN_USERNAME", "").strip()
    password = env.get("APP_ADMIN_PASSWORD", "")
    if not username or len(username) > 200 or any(char.isspace() or char == ":" for char in username):
        raise ConfigurationError("APP_ADMIN_USERNAME must be set to a username without spaces or colons")
    if len(password) < 12 or password.isspace():
        raise ConfigurationError("APP_ADMIN_PASSWORD must be set to at least 12 characters")
    return username, password
