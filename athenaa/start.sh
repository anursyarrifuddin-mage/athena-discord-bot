#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# ATHENAA STARTUP SCRIPT (VPS / PTERODACTYL SINGLE-INSTANCE)
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p data logs modules backups

if [ ! -f ".env" ] && [ -f "../.env" ]; then
  cp "../.env" ".env"
fi

PYTHON_BIN="python3"
if ! command -v python3 >/dev/null 2>&1 && command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

echo "[Athenaa] Memeriksa lingkungan Python dan FFmpeg..."
$PYTHON_BIN --version
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -version | head -n 1
else
  echo "[PERINGATAN] FFmpeg belum ditemukan di PATH. Pastikan image Pterodactyl menyertakan FFmpeg untuk voice Discord."
fi

# Pastikan PYTHONPATH menyertakan direktori kerja saat ini dan hanya 1 worker dijalankan
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"
export WEB_HOST="${WEB_HOST:-0.0.0.0}"
export WEB_PORT="${SERVER_PORT:-${WEB_PORT:-10031}}"

echo "[Athenaa] Menjalankan aplikasi pada ${WEB_HOST}:${WEB_PORT}..."
exec "$PYTHON_BIN" -m app.main

