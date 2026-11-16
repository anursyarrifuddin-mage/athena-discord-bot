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
    web_base_url: str = field(default_factory=lambda: _clean_env("WEB_BASE_URL", "https://bot.athenaa.my.id"))

    discord_token: str = field(default_factory=lambda: _clean_env("DISCORD_TOKEN"))
    discord_client_id: str = field(default_factory=lambda: _clean_env("DISCORD_CLIENT_ID"))
    discord_client_secret: str = field(default_factory=lambda: _clean_env("DISCORD_CLIENT_SECRET"))
    discord_redirect_uri: str = field(
        default_factory=lambda: _clean_env("DISCORD_REDIRECT_URI", "https://bot.athenaa.my.id/auth/callback")
    )

    main_guild_id: str = field(default_factory=lambda: _clean_env("MAIN_GUILD_ID", "1428666546942902294"))
    owner_discord_id: str = field(default_factory=lambda: _clean_env("OWNER_DISCORD_ID", "844174494099701780"))
    dj_role_id: str = field(default_factory=lambda: _clean_env("DJ_ROLE_ID", "1563848335247417395"))
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
        default_factory=lambda: _clean_env("GOOGLE_REDIRECT_URI", "https://bot.athenaa.my.id/auth/callback")
    )

    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))

    # AI Smart Trending Autoplay & RAM Optimization Settings
    ai_autoplay_enabled: bool = field(
        default_factory=lambda: os.environ.get("AI_AUTOPLAY_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    )
    ai_autoplay_model: str = field(
        default_factory=lambda: _clean_env("AI_AUTOPLAY_MODEL", "gemini-3.8-flash")
    )
    ai_autoplay_fallback_models: str = field(
        default_factory=lambda: _clean_env(
            "AI_AUTOPLAY_FALLBACK_MODELS",
            "gemini-3.8-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash,gemini-2.5-flash-lite",
        )
    )
    gemini_api_key: str = field(
        default_factory=lambda: _clean_env("GEMINI_API_KEY", "")
    )
    gemini_api_keys: str = field(
        default_factory=lambda: _clean_env("GEMINI_API_KEYS", "")
    )
    ambience_rain_url: str = field(
        default_factory=lambda: _clean_env("AMBIENCE_RAIN_URL", "https://www.youtube.com/watch?v=jfKfPfyJRdk")
    )
    ambience_cafe_url: str = field(
        default_factory=lambda: _clean_env("AMBIENCE_CAFE_URL", "https://www.youtube.com/watch?v=lP26UCnoH9s")
    )
    ambience_lofi_url: str = field(
        default_factory=lambda: _clean_env("AMBIENCE_LOFI_URL", "https://www.youtube.com/watch?v=5qap5aO4i9A")
    )
    ambience_night_coding_url: str = field(
        default_factory=lambda: _clean_env("AMBIENCE_NIGHT_CODING_URL", "https://www.youtube.com/watch?v=4xDzrJKXOOY")
    )
    ambience_piano_url: str = field(
        default_factory=lambda: _clean_env("AMBIENCE_PIANO_URL", "https://www.youtube.com/watch?v=1ZYbU82GVz4")
    )
    low_memory_mode: bool = field(
        default_factory=lambda: os.environ.get("LOW_MEMORY_MODE", "true").strip().lower() in ("1", "true", "yes", "on")
    )
    audio_cache_max_files: int = field(
        default_factory=lambda: max(1, int(os.environ.get("AUDIO_CACHE_MAX_FILES", "5")))
    )
    audio_cache_max_mb: int = field(
        default_factory=lambda: max(10, int(os.environ.get("AUDIO_CACHE_MAX_MB", "60")))
    )
    gc_interval_seconds: int = field(
        default_factory=lambda: max(30, int(os.environ.get("GC_INTERVAL_SECONDS", "180")))
    )
    ffmpeg_threads: int = field(
        default_factory=lambda: max(1, int(os.environ.get("FFMPEG_THREADS", "1")))
    )

    def get_ambience_url(self, tema: str) -> str:
        """Mengambil link musik /ambience sesuai tema dari .env."""
        t = (tema or "rain").strip().lower()
        if t.startswith(("http://", "https://")):
            return t
        env_map = {
            "rain": os.environ.get("AMBIENCE_RAIN_URL", "").strip() or self.ambience_rain_url,
            "cafe": os.environ.get("AMBIENCE_CAFE_URL", "").strip() or self.ambience_cafe_url,
            "lofi": os.environ.get("AMBIENCE_LOFI_URL", "").strip() or self.ambience_lofi_url,
            "night_coding": os.environ.get("AMBIENCE_NIGHT_CODING_URL", "").strip() or self.ambience_night_coding_url,
            "piano": os.environ.get("AMBIENCE_PIANO_URL", "").strip() or self.ambience_piano_url,
        }
        return env_map.get(t, env_map["rain"])

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
            "ai_smart_autoplay": bool(self.ai_autoplay_enabled),
            "ram_optimizer": bool(self.low_memory_mode),
        }


settings = AppConfig()
settings.ensure_directories()
