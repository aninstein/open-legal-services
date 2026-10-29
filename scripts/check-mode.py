"""Check deployment selection without printing the environment or secrets."""

import json
import os
import sys
from pathlib import Path


def dotenv() -> dict[str, str]:
    result = dict(os.environ)
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key.strip()] = value
    return result


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode != "external":
        raise SystemExit("Usage: ./scripts/up.sh [external]")
    values = dotenv()
    try:
        entries = [item for item in json.loads(values["MODEL_CONFIG_JSON"]) if item.get("enabled", True)]
        primary = values.get("PRIMARY_MODEL", "")
        model = next((item for item in entries if item["model"] == primary), entries[0])
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise SystemExit("Configure a valid MODEL_CONFIG_JSON and PRIMARY_MODEL in .env") from exc
    key_env = model.get("api_key_env", "")
    if model.get("provider") != "openai" or not key_env or not values.get(key_env):
        raise SystemExit("Online mode requires an OpenAI-compatible primary with a populated api_key_env")


if __name__ == "__main__":
    main()
