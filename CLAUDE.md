# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A web-based distributed log search tool that searches logs across remote servers via SSH and Kubernetes pods via kubectl. The backend is a single-file Flask app (`app.py`) with a vanilla HTML/JS frontend. Data is persisted as JSON (`data/systems.json`).

## Commands

```bash
# Start/stop the app (runs on port 5001)
./start.sh start
./start.sh stop
./start.sh restart
./start.sh status

# Install dependencies (offline-capable)
./libs/install.sh

# Manual dependency install from offline wheels
pip3 install --no-index --find-links=libs flask paramiko
```

No test suite or linter is configured.

## Architecture

**Backend (`app.py`):** Single-file Flask application containing all routes, SSH logic, K8s integration, and data persistence. Key components:

- **Password encryption:** Server passwords are XOR-encrypted with a SHA-256 hash of a secret key (`data/.secret_key`). The `encrypt_password`/`decrypt_password` functions handle this transparently in `load_data`/`save_data`.
- **SSH search flow (`search_server_logs`):** Connects to remote servers via Paramiko, uses `find` to discover log files (filtered by `filename_pattern`), then `grep -F -n -i` with context lines. Results are reversed (newest first). Retries once on failure.
- **K8s search flow (`search_k8s_target`):** Uses `kubectl` subprocess calls to list pods (filtered by `pod_pattern`), fetch logs (`--tail=5000`), then greps locally. Also retries once.
- **Streaming endpoint (`/api/search/stream`):** SSE (Server-Sent Events) that yields results per server/target as they complete.
- **Data model:** Systems contain `servers[]` (SSH targets) and `k8s_targets[]` (Kubernetes targets). Both are edited via index-based REST APIs.

**Frontend:** Two static HTML pages — `index.html` (server/system management) and `search.html` (log search UI with real-time streaming results).

**Data storage:** `data/systems.json` — read/written on every API call (no database). Passwords are encrypted at rest.

## Key Conventions

- All user-facing strings (API responses, logs, UI) are in Chinese.
- Logging uses a custom logger (`log_search`) with daily rotation (30-day retention) to `logs/app.log`.
- SSH connections use `AutoAddPolicy` (auto-accepts host keys) and 15-second keepalive.
- File matching patterns are comma-separated keywords used in `find -name '*pattern*'`.
- Search keyword max length is 200 characters; context lines range 0-50.
