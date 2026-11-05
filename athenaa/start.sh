#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# ATHENAA STARTUP SCRIPT (VPS / PTERODACTYL SINGLE-INSTANCE)
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p data logs modules

if [ ! -f ".env" ] && [ -f "../.env" ]; then
  cp "../.env" ".env"
fi

echo "[Athenaa] Memeriksa lingkungan Python dan FFmpeg..."
python3 --version
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -version | head -n 1
else
  echo "[PERINGATAN] FFmpeg belum ditemukan di PATH. Pemutaran voice Discord memerlukan FFmpeg."
fi

# Pastikan hanya 1 worker dijalankan agar koneksi Gateway Discord tidak ganda
export WEB_HOST="${WEB_HOST:-0.0.0.0}"
export WEB_PORT="${SERVER_PORT:-${WEB_PORT:-10031}}"

echo "[Athenaa] Menjalankan aplikasi pada ${WEB_HOST}:${WEB_PORT}..."
exec python3 -m app.main
