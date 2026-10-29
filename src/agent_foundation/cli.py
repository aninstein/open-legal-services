"""Operator diagnostics that never print credentials."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .config import ConfigurationError, admin_credentials, load_models
from .deerflow import DEERFLOW_COMMIT
from .voice import speech_endpoint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["doctor"])
    args = parser.parse_args()
    load_dotenv(Path.cwd() / ".env")
    if args.command == "doctor":
        try:
            models = load_models()
            admin_credentials()
            stt = speech_endpoint("stt")
            tts = speech_endpoint("tts")
        except ConfigurationError as exc:
            raise SystemExit(f"Configuration error: {exc}") from exc
        print(json.dumps({"ready": True, "deerflow_commit": DEERFLOW_COMMIT,
                          "models": [{"model": model.model, "provider": model.provider} for model in models],
                          "voice": {"stt": stt is not None, "tts": tts is not None}}, indent=2))


if __name__ == "__main__":
    main()
