"""
Konfigurasi Terpusat Aplikasi Athenaa (Discord Bot + Web Dashboard).
Membaca seluruh variabel dari environment / file .env tanpa nilai kredensial hardcoded.
Sistem Peran Per-Server: Admin Server, DJ, dan Member (tanpa ketergantungan OWNER_DISCORD_ID).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
MODULES_DIR = BASE_DIR / "modules"
BACKUPS_DIR = DATA_DIR / "backups"


def _load_dotenv_if_present(env_path: Path) -> None:
    """Memuat pasangan KEY=VALUE dari file .env lokal jika belum diset di os.environ."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and (key not in os.environ or not os.environ.get(key)):
            os.environ[key] = value


_load_dotenv_if_present(BASE_DIR / ".env")
_load_dotenv_if_present(BASE_DIR.parent / ".env")


<<<<<<< HEAD
def _resolve_discord_client_id() -> str:
    raw_cid = os.getenv("DISCORD_CLIENT_ID", "").strip()
    if raw_cid.isdigit() and len(raw_cid) >= 15:
        return raw_cid
    raw_tok = os.getenv("DISCORD_TOKEN", "").strip()
    if raw_tok and "." in raw_tok:
        try:
            import base64
            first_part = raw_tok.split(".", 1)[0]
            padded = first_part + ("=" * ((4 - len(first_part) % 4) % 4))
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore").strip()
            if decoded.isdigit() and len(decoded) >= 15:
                return decoded
        except Exception:
            pass
    return ""


def _resolve_discord_client_secret() -> str:
    raw_sec = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
    if not raw_sec or "your_client_secret" in raw_sec.lower() or "placeholder" in raw_sec.lower():
        return ""
    return raw_sec


=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
@dataclass(frozen=True)
class AppSettings:
    """Objek konfigurasi aplikasi yang divalidasi saat startup."""

    # Discord Bot & OAuth2
    discord_token: str = field(default_factory=lambda: os.getenv("DISCORD_TOKEN", "").strip())
<<<<<<< HEAD
    discord_client_id: str = field(default_factory=_resolve_discord_client_id)
    discord_client_secret: str = field(default_factory=_resolve_discord_client_secret)
=======
    discord_client_id: str = field(default_factory=lambda: os.getenv("DISCORD_CLIENT_ID", "").strip())
    discord_client_secret: str = field(default_factory=lambda: os.getenv("DISCORD_CLIENT_SECRET", "").strip())
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    discord_redirect_uri: str = field(
        default_factory=lambda: os.getenv(
            "DISCORD_REDIRECT_URI", "http://localhost:3000/auth/discord/callback"
        ).strip()
    )
    # Deprecated legacy field kept empty so per-server Admin / DJ / Member roles are used everywhere
    owner_discord_id: str = ""
    main_guild_id: str = field(
        default_factory=lambda: os.getenv("MAIN_GUILD_ID", "1428666546942902294").strip() or "1428666546942902294"
    )
    dj_role_id: str = field(
        default_factory=lambda: os.getenv("DJ_ROLE_ID", "1482041664024084691").strip() or "1482041664024084691"
    )
    task_reminder_channel_id: str = field(
        default_factory=lambda: os.getenv("TASK_REMINDER_CHANNEL_ID", "1428666547701809160").strip()
        or "1428666547701809160"
    )

    # Moodle / Waskita Automated Calendar & Login Sync
    moodle_ical_url: str = field(default_factory=lambda: os.getenv("MOODLE_ICAL_URL", "").strip())
    moodle_base_url: str = field(
        default_factory=lambda: os.getenv("MOODLE_BASE_URL", "https://waskita.amikom.ac.id").strip().rstrip("/")
    )
    moodle_username: str = field(default_factory=lambda: os.getenv("MOODLE_USERNAME", "").strip())
    moodle_password: str = field(default_factory=lambda: os.getenv("MOODLE_PASSWORD", "").strip())

    # Google Classroom OAuth2 (Opsional)
    google_client_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID", "").strip())
    google_client_secret: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_SECRET", "").strip())
    google_redirect_uri: str = field(
        default_factory=lambda: os.getenv(
            "GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/google/callback"
        ).strip()
    )

    # Web Server & Keamanan
    web_host: str = field(default_factory=lambda: os.getenv("WEB_HOST", "0.0.0.0").strip() or "0.0.0.0")
    web_port: int = field(
        default_factory=lambda: int(
            os.getenv("SERVER_PORT")
            or os.getenv("WEB_PORT")
            or "10031"
        )
    )
    web_base_url: str = field(
        default_factory=lambda: os.getenv(
            "WEB_BASE_URL",
            f"http://localhost:{os.getenv('SERVER_PORT') or os.getenv('WEB_PORT') or '10031'}",
        ).strip()
    )
    custom_logo_url: str = field(
        default_factory=lambda: os.getenv("CUSTOM_LOGO_URL", "/logo.png").strip() or "/logo.png"
    )
    session_secret: str = field(
        default_factory=lambda: os.getenv("SESSION_SECRET", "").strip()
        or "athenaa-default-session-secret-key-2026"
    )
    encryption_key: str = field(
        default_factory=lambda: os.getenv("ENCRYPTION_KEY", "").strip()
        or "athenaa-default-encryption-key-2026"
    )
    backup_encryption_key: str = field(
        default_factory=lambda: os.getenv("BACKUP_ENCRYPTION_KEY", "").strip()
        or "athenaa-default-backup-key-2026"
    )

<<<<<<< HEAD
    @property
    def encryption_secret(self) -> str:
        return self.encryption_key or self.session_secret

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    # Database & Direktori Penyimpanan
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", f"sqlite:///{(DATA_DIR / 'athenaa.db').as_posix()}"
        ).strip()
    )
    sqlite_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("SQLITE_PATH", str(DATA_DIR / "athenaa.db"))
        )
    )
    modules_dir: Path = field(default_factory=lambda: MODULES_DIR)
    backups_dir: Path = field(default_factory=lambda: BACKUPS_DIR)
    logs_dir: Path = field(default_factory=lambda: LOGS_DIR)

    # Operasional & Batasan File
    default_timezone: str = field(
        default_factory=lambda: os.getenv("DEFAULT_TIMEZONE", "Asia/Jakarta").strip() or "Asia/Jakarta"
    )
    max_attachment_mb: int = field(
        default_factory=lambda: int(os.getenv("MAX_ATTACHMENT_MB", "15") or "15")
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())

    def ensure_directories(self) -> None:
        """Memastikan seluruh direktori penyimpanan lokal tersedia."""
        for directory in (DATA_DIR, self.modules_dir, self.backups_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def validate_startup(self) -> List[str]:
        """Mengembalikan daftar peringatan konfigurasi tanpa menghentikan paksa server."""
        warnings: List[str] = []
        if not self.discord_token:
            warnings.append(
                "DISCORD_TOKEN belum diatur di .env. Web Dashboard & API tetap berjalan penuh; "
                "isi DISCORD_TOKEN untuk mengaktifkan koneksi Voice & Slash Command bot Discord."
            )
        if not self.discord_client_id or not self.discord_client_secret:
            warnings.append(
                "DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET belum lengkap. Login OAuth2 Discord "
                "akan menggunakan mode sesi lokal sampai kredensial OAuth2 diisi."
            )
        return warnings


settings = AppSettings()
settings.ensure_directories()

from .loader import (
    load_constants,
    load_radio_stations,
    reload_all_configs,
    get_curated_catalog,
    get_curated_radio_pools,
    get_indonesian_artists,
    get_western_artists,
    get_all_known_artists,
    get_genre_keywords,
    get_Artist_similarity_map,
    get_block_patterns,
    get_strip_patterns,
    get_duration_limits,
    get_viral_views_threshold,
    get_radio_stations,
    get_radio_station_by_key,
    get_radio_stations_by_genre,
    get_default_fallback_radio,
    ConfigLoadError,
)

__all__ = [
    "AppSettings",
    "settings",
    "BASE_DIR",
    "DATA_DIR",
    "LOGS_DIR",
    "MODULES_DIR",
    "BACKUPS_DIR",
    "load_constants",
    "load_radio_stations",
    "reload_all_configs",
    "get_curated_catalog",
    "get_curated_radio_pools",
    "get_indonesian_artists",
    "get_western_artists",
    "get_all_known_artists",
    "get_genre_keywords",
    "get_Artist_similarity_map",
    "get_block_patterns",
    "get_strip_patterns",
    "get_duration_limits",
    "get_viral_views_threshold",
    "get_radio_stations",
    "get_radio_station_by_key",
    "get_radio_stations_by_genre",
    "get_default_fallback_radio",
    "ConfigLoadError",
]