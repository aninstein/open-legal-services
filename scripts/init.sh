#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
if [[ ! -f .env ]]; then cp .env.example .env; fi
chmod 600 .env
printf '%s\n' 'Initialized private .env. Configure the model, then start the service and register a user.'
