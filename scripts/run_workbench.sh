#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

# Docker Compose owns only the isolated workbench stack and named volume.
docker compose -f compose.workbench.yml up --build -d
printf '\nGate Triage: http://127.0.0.1:8088\nAPI docs: http://127.0.0.1:8088/docs\n'
