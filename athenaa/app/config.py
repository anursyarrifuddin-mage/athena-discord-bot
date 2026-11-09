"""
Konfigurasi Terpusat Aplikasi Athenaa (Discord Bot + Web Dashboard).
Membaca seluruh variabel dari environment / file .env tanpa nilai kredensial hardcoded.
Sistem Peran Per-Server: Admin Server, DJ, dan Member (tanpa ketergantungan OWNER_DISCORD_ID).
"""

from __future__ import annotations

from app.config import (
    AppSettings,
    BACKUPS_DIR,
    BASE_DIR,
    DATA_DIR,
    LOGS_DIR,
    MODULES_DIR,
    settings,
)

__all__ = [
    "AppSettings",
    "settings",
    "BASE_DIR",
    "DATA_DIR",
    "LOGS_DIR",
    "MODULES_DIR",
    "BACKUPS_DIR",
]
