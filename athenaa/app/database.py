"""
Modul Database & Migrasi Skema Aman (SQLite + SQLAlchemy Compatible).
Mendukung operasi sinkron dan asinkron menggunakan sqlite3 stdlib dan SQLAlchemy
dengan pembuatan skema idempoten (CREATE TABLE IF NOT EXISTS) tanpa menghapus data lama.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from app.config import settings

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id TEXT PRIMARY KEY,
    guild_name TEXT NOT NULL,
    music_channel_id TEXT DEFAULT '',
    task_channel_id TEXT DEFAULT '',
    dj_role_id TEXT DEFAULT '',
    moodle_ics_url_encrypted TEXT DEFAULT '',
    moodle_last_sync TEXT DEFAULT '',
    classroom_connected INTEGER DEFAULT 0,
    classroom_last_sync TEXT DEFAULT '',
    reminder_days_before INTEGER DEFAULT 3,
    timezone TEXT DEFAULT 'Asia/Jakarta',
    idle_timeout_seconds INTEGER DEFAULT 300,
    mode_247 INTEGER DEFAULT 0,
    autoplay INTEGER DEFAULT 1,
    exp_cooldown_seconds INTEGER DEFAULT 60,
    exp_per_message INTEGER DEFAULT 15,
    max_attachment_mb INTEGER DEFAULT 15,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    avatar_url TEXT DEFAULT '',
    preferred_locale TEXT DEFAULT 'id-ID',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS music_sessions (
    guild_id TEXT PRIMARY KEY,
    voice_channel_id TEXT DEFAULT '',
    voice_channel_name TEXT DEFAULT 'General Voice',
    host_user_id TEXT DEFAULT '',
    host_username TEXT DEFAULT '',
    current_item_id TEXT DEFAULT '',
    is_playing INTEGER DEFAULT 0,
    is_paused INTEGER DEFAULT 0,
    position_sec INTEGER DEFAULT 0,
    volume INTEGER DEFAULT 80,
    loop_mode TEXT DEFAULT 'off',
    autoplay INTEGER DEFAULT 1,
    mode_247 INTEGER DEFAULT 0,
    active_radio_name TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS queue_items (
    item_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT DEFAULT '',
    duration_sec INTEGER DEFAULT 0,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    stream_url TEXT DEFAULT '',
    thumbnail_url TEXT DEFAULT '',
    requester_id TEXT NOT NULL,
    requester_name TEXT NOT NULL,
    added_at TEXT NOT NULL,
    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_queue_guild_pos ON queue_items(guild_id, position);

CREATE TABLE IF NOT EXISTS favorites (
    favorite_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT DEFAULT '',
    duration_sec INTEGER DEFAULT 0,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    thumbnail_url TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(user_id, source_url)
);

CREATE TABLE IF NOT EXISTS playlists (
    playlist_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS playlist_items (
    id TEXT PRIMARY KEY,
    playlist_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT DEFAULT '',
    duration_sec INTEGER DEFAULT 0,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    thumbnail_url TEXT DEFAULT '',
    FOREIGN KEY (playlist_id) REFERENCES playlists(playlist_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    external_uid TEXT DEFAULT '',
    course_name TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'manual',
    deadline_iso TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Jakarta',
    source_url TEXT DEFAULT '',
    is_completed INTEGER DEFAULT 0,
    completed_by TEXT DEFAULT '',
    completed_at TEXT DEFAULT '',
    created_by TEXT NOT NULL,
    last_synced_at TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_tasks_guild_deadline ON tasks(guild_id, deadline_iso);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_guild_ext_uid
    ON tasks(guild_id, external_uid) WHERE external_uid != '';

CREATE TABLE IF NOT EXISTS task_attachments (
    attachment_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    uploaded_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reminder_deliveries (
    delivery_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    delivered_at TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(task_id, stage),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS integration_connections (
    connection_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    encrypted_credentials TEXT DEFAULT '',
    last_sync_at TEXT DEFAULT '',
    last_error TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE(guild_id, provider)
);

CREATE TABLE IF NOT EXISTS level_profiles (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    current_exp INTEGER NOT NULL DEFAULT 0,
    total_messages INTEGER NOT NULL DEFAULT 0,
    last_exp_at TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS afk_statuses (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    reason TEXT NOT NULL,
    started_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS web_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    role TEXT NOT NULL,
    csrf_token TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discord_sessions (
    user_id TEXT PRIMARY KEY,
    session_token TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL,
    discord_tag TEXT NOT NULL,
    role_label TEXT NOT NULL,
    is_owner INTEGER NOT NULL DEFAULT 0,
    has_dj_role INTEGER NOT NULL DEFAULT 0,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class DatabaseManager:
    """Manajer koneksi SQLite dengan migrasi skema idempoten dan dukungan transaksi."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else settings.sqlite_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            conn.executescript(SCHEMA_SQL)
            # Bersihkan data dummy lama jika pernah ada di database
            dummy_guilds = ("109283746510293847", "209384756102938475")
            dummy_users = (
                "998877665544332211",
                "223344556677889900",
                "334455667788990011",
                "445566778899001122",
                "556677889900112233",
            )
            conn.executemany("DELETE FROM guild_settings WHERE guild_id = ?", [(g,) for g in dummy_guilds])
            conn.executemany("DELETE FROM discord_sessions WHERE user_id = ?", [(u,) for u in dummy_users])
            conn.executemany("DELETE FROM level_profiles WHERE user_id = ?", [(u,) for u in dummy_users])
            conn.executemany("DELETE FROM afk_statuses WHERE user_id = ?", [(u,) for u in dummy_users])
            conn.executemany("DELETE FROM favorites WHERE user_id = ?", [(u,) for u in dummy_users])
            conn.executemany("DELETE FROM playlists WHERE owner_user_id = ?", [(u,) for u in dummy_users])

            # Migrasi otomatis jika ada record lama yang masih menyimpan URL Apple Music / iTunes
            conn.execute(
                """
                UPDATE queue_items
                SET source_type = 'youtube',
                    source_url = 'https://www.youtube.com/results?search_query=' || replace(title || ' ' || artist, ' ', '+'),
                    stream_url = ''
                WHERE source_type = 'itunes_preview' OR source_url LIKE '%apple.com%' OR stream_url LIKE '%apple.com%'
                """
            )
            conn.execute(
                """
                UPDATE favorites
                SET source_type = 'youtube',
                    source_url = 'https://www.youtube.com/results?search_query=' || replace(title || ' ' || artist, ' ', '+')
                WHERE source_type = 'itunes_preview' OR source_url LIKE '%apple.com%'
                """
            )
            conn.execute(
                """
                UPDATE playlist_items
                SET source_type = 'youtube',
                    source_url = 'https://www.youtube.com/results?search_query=' || replace(title || ' ' || artist, ' ', '+')
                WHERE source_type = 'itunes_preview' OR source_url LIKE '%apple.com%'
                """
            )

            # Pastikan server Discord utama terdaftar (TK1GACORKINK)
            conn.execute(
                """
                INSERT INTO guild_settings (
                    guild_id, guild_name, music_channel_id, task_channel_id,
                    dj_role_id, timezone, mode_247, autoplay, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'Asia/Jakarta', 1, 1, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    guild_name = CASE
                        WHEN guild_settings.guild_name IN ('Athenaa Server Utama', 'Informatika & Musik Hub (Server Utama)')
                        THEN excluded.guild_name
                        ELSE guild_settings.guild_name
                    END,
                    task_channel_id = CASE
                        WHEN guild_settings.task_channel_id = '' OR guild_settings.task_channel_id = '1558142572164022362'
                        THEN excluded.task_channel_id
                        ELSE guild_settings.task_channel_id
                    END
                """,
                (
                    settings.main_guild_id,
                    "TK1GACORKINK",
                    "1428666547701809159",
                    settings.task_reminder_channel_id,
                    settings.dj_role_id,
                    now_iso,
                ),
            )

            # Pastikan profil RPG Owner di server utama tersedia untuk Leaderboard
            conn.execute(
                """
                INSERT INTO level_profiles (
                    guild_id, user_id, username, display_name, level, current_exp,
                    total_messages, last_exp_at, updated_at
                ) VALUES (?, ?, 'filisim', 'Aetheriaaa', 14, 340, 412, ?, ?)
                ON CONFLICT(guild_id, user_id) DO NOTHING
                """,
                (settings.main_guild_id, settings.owner_discord_id, now_iso, now_iso),
            )


db_manager = DatabaseManager()

