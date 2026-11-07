"""
Modul Konfigurasi Lingkungan (Environment Configuration).
Memuat variabel dari .env atau environment OS tanpa menyimpan kredensial hardcoded.
Menyediakan pemeriksaan kesiapan fitur secara terpisah agar ketiadaan konfigurasi opsional
(seperti Moodle atau Google Classroom) tidak menghentikan fitur inti lainnya.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv_fallback(dotenv_path: Path) -> None:
    """Memuat file .env secara aman bahkan jika python-dotenv belum terinstal."""
    if not dotenv_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(dotenv_path)
        return
    except ImportError:
        pass

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_fallback(BASE_DIR / ".env")
_load_dotenv_fallback(BASE_DIR.parent / ".env")

PLACEHOLDER_VALUES = {
    "",
    "MY_GEMINI_API_KEY",
    "MY_APP_URL",
    "https://example.com",
    "https://example.com/auth/callback",
    "https://example.com/auth/google/callback",
    "YOUR_DISCORD_TOKEN",
    "CHANGE_ME",
}


def _clean_env(name: str, default: str = "") -> str:
    val = os.environ.get(name, default).strip()
    if val in PLACEHOLDER_VALUES:
        return default if default not in PLACEHOLDER_VALUES else ""
    return val


@dataclass(frozen=True)
class AppConfig:
    web_host: str = field(default_factory=lambda: os.environ.get("WEB_HOST", "0.0.0.0"))
    web_port: int = field(default_factory=lambda: int(os.environ.get("WEB_PORT", "10031")))
    web_base_url: str = field(default_factory=lambda: _clean_env("WEB_BASE_URL", "https://athenaa.my.id"))

    discord_token: str = field(default_factory=lambda: _clean_env("DISCORD_TOKEN"))
    discord_client_id: str = field(default_factory=lambda: _clean_env("DISCORD_CLIENT_ID"))
    discord_client_secret: str = field(default_factory=lambda: _clean_env("DISCORD_CLIENT_SECRET"))
    discord_redirect_uri: str = field(
        default_factory=lambda: _clean_env("DISCORD_REDIRECT_URI", "https://athenaa.my.id/auth/callback")
    )

    main_guild_id: str = field(default_factory=lambda: _clean_env("MAIN_GUILD_ID"))
    owner_discord_id: str = field(default_factory=lambda: _clean_env("OWNER_DISCORD_ID"))
    dj_role_id: str = field(default_factory=lambda: _clean_env("DJ_ROLE_ID", "role-dj"))
    task_reminder_channel_id: str = field(
        default_factory=lambda: (
            _clean_env("TASK_REMINDER_CHANNEL_ID")
            or _clean_env("TASK_CHANNEL_ID")
            or _clean_env("DISCORD_REMINDER_CHANNEL_ID")
            or "1558142572164022362"
        )
    )

    custom_logo_url: str = field(default_factory=lambda: _clean_env("CUSTOM_LOGO_URL"))
    database_url: str = field(
        default_factory=lambda: os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'athenaa.db'}")
    )
    sqlite_path: Path = field(
        default_factory=lambda: Path(os.environ.get("SQLITE_PATH", str(BASE_DIR / "data" / "athenaa.db")))
    )
    modules_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("MODULES_DIR", str(BASE_DIR / "modules")))
    )
    backups_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("BACKUPS_DIR", str(BASE_DIR / "data" / "backups")))
    )
    logs_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("LOGS_DIR", str(BASE_DIR / "logs")))
    )

    session_secret: str = field(
        default_factory=lambda: _clean_env("SESSION_SECRET", "athenaa-dev-ephemeral-session-key-change-in-prod")
    )
    encryption_key: str = field(
        default_factory=lambda: _clean_env("ENCRYPTION_KEY", "athenaa-dev-encryption-key-32bytes!")
    )
    backup_encryption_key: str = field(
        default_factory=lambda: _clean_env("BACKUP_ENCRYPTION_KEY", "athenaa-dev-backup-key-32bytes!!")
    )

    default_timezone: str = field(default_factory=lambda: os.environ.get("DEFAULT_TIMEZONE", "Asia/Jakarta"))
    max_attachment_mb: int = field(default_factory=lambda: int(os.environ.get("MAX_ATTACHMENT_MB", "15")))

    moodle_base_url: str = field(default_factory=lambda: _clean_env("MOODLE_BASE_URL", "https://lms.kampus.ac.id"))
    moodle_ical_url: str = field(default_factory=lambda: _clean_env("MOODLE_ICAL_URL"))
    moodle_username: str = field(default_factory=lambda: _clean_env("MOODLE_USERNAME"))
    moodle_password: str = field(default_factory=lambda: _clean_env("MOODLE_PASSWORD"))

    google_client_id: str = field(default_factory=lambda: _clean_env("GOOGLE_CLIENT_ID"))
    google_client_secret: str = field(default_factory=lambda: _clean_env("GOOGLE_CLIENT_SECRET"))
    google_redirect_uri: str = field(
        default_factory=lambda: _clean_env("GOOGLE_REDIRECT_URI", "http://localhost:10031/auth/google/callback")
    )

    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))

    def ensure_directories(self) -> None:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.modules_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def feature_readiness(self) -> Dict[str, bool]:
        """Mengembalikan status kesiapan tiap subsistem berdasarkan kredensial nyata."""
        return {
            "discord_bot": bool(self.discord_token),
            "discord_oauth": bool(self.discord_client_id and self.discord_client_secret),
            "moodle_env": bool(self.moodle_ical_url or (self.moodle_username and self.moodle_password)),
            "google_classroom": bool(self.google_client_id and self.google_client_secret),
            "custom_encryption_key": "athenaa-dev-" not in self.encryption_key,
            "custom_backup_key": "athenaa-dev-" not in self.backup_encryption_key,
        }


settings = AppConfig()
settings.ensure_directories()
