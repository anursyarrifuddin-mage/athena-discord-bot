"""
Modul FastAPI REST API, WebSocket (/ws), Discord OAuth2 Multi-Device Auth (Maks. 5 Sesi),
dan Static SPA Hosting untuk Athenaa Web Dashboard (Pterodactyl Port 10031 / athenaa.my.id).
Menyinkronkan kondisi asli Discord Bot VoiceClient dengan Web Player secara real-time.
"""

import asyncio
import base64
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect  # type: ignore
    from fastapi.middleware.cors import CORSMiddleware  # type: ignore
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse  # type: ignore
    from fastapi.staticfiles import StaticFiles  # type: ignore

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = Any  # type: ignore
    HTTPException = Exception  # type: ignore
    Request = Any  # type: ignore
    WebSocket = Any  # type: ignore
    WebSocketDisconnect = Exception  # type: ignore
    CORSMiddleware = Any  # type: ignore
    FileResponse = Any  # type: ignore
    HTMLResponse = Any  # type: ignore
    JSONResponse = Any  # type: ignore
    PlainTextResponse = Any  # type: ignore
    RedirectResponse = Any  # type: ignore
    StaticFiles = Any  # type: ignore

    def Query(default: Any = None, **_kwargs: Any) -> Any:  # type: ignore
        return default

from app.cli_bridge import create_source_zip, run_test_suite
from app.config import BASE_DIR, settings
from app.database import db_manager
from app.security.validators import (
    SlidingWindowRateLimiter,
<<<<<<< HEAD
    generate_oauth_state,
    sanitize_and_validate_attachment,
    sanitize_discord_outbound_text,
    validate_snowflake_param,
    verify_oauth_state,
=======
    sanitize_and_validate_attachment,
    validate_snowflake_param,
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
)
from app.services.academy_service import AcademyService
from app.services.backup_service import BackupService
from app.services.leveling_service import LevelingService
from app.services.lyrics_service import lyrics_service
from app.services.music_service import (
    VERIFIED_RADIO_STATIONS,
    classify_music_input,
    extract_spotify_playlist_tracks,
    extract_youtube_playlist_tracks,
    resolve_browser_preview_stream,
    resolve_spotify_link,
    search_songs_with_singer,
)
from app.services.queue import GuildQueueState, queue_service

START_TIME = time.time()
MAX_SESSIONS_PER_USER = 5
rate_limiter = SlidingWindowRateLimiter(max_requests=90, window_seconds=60)
academy_service = AcademyService()
leveling_service = LevelingService()
backup_service = BackupService()

def _resolve_static_dir() -> Path:
    candidates = [
        BASE_DIR / "app" / "web" / "static",
        Path(__file__).resolve().parent.parent / "static",
        BASE_DIR.parent / "dist",
        Path("app/web/static"),
        Path("dist"),
    ]
    for cand in candidates:
        try:
            if (cand / "index.html").is_file():
                return cand
        except Exception:
            pass
    return BASE_DIR / "app" / "web" / "static"


STATIC_DIR = _resolve_static_dir()

UI_CUSTOMIZATION_INJECTION = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_multi_session_table() -> None:
    """Memastikan tabel discord_user_sessions dan user_guild_roles tersedia untuk per-server RBAC."""
    try:
        with db_manager.transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discord_user_sessions (
                    session_token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    discord_tag TEXT NOT NULL,
<<<<<<< HEAD
                    avatar_url TEXT DEFAULT '',
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                    role_label TEXT NOT NULL,
                    is_owner INTEGER NOT NULL DEFAULT 0,
                    has_dj_role INTEGER NOT NULL DEFAULT 0,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
<<<<<<< HEAD
            try:
                cols = [r["name"] for r in conn.execute("PRAGMA table_info(discord_user_sessions)").fetchall()]
                if "avatar_url" not in cols:
                    conn.execute("ALTER TABLE discord_user_sessions ADD COLUMN avatar_url TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                cols_legacy = [r["name"] for r in conn.execute("PRAGMA table_info(discord_sessions)").fetchall()]
                if "avatar_url" not in cols_legacy:
                    conn.execute("ALTER TABLE discord_sessions ADD COLUMN avatar_url TEXT DEFAULT ''")
            except Exception:
                pass
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_discord_user_sessions_uid ON discord_user_sessions(user_id, created_at ASC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_guild_roles (
                    user_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'member',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, guild_id)
                )
                """
            )
    except Exception:
        pass


_ensure_multi_session_table()


def _set_user_guild_role(user_id: str, guild_id: str, role: str) -> None:
    clean_uid = str(user_id or "").strip()
    clean_gid = str(guild_id or "").strip()
    clean_role = str(role or "member").strip().lower()
    if clean_role not in ("admin", "dj", "member"):
        clean_role = "member"
    if not clean_uid or not clean_gid:
        return
    _ensure_multi_session_table()
    try:
        with db_manager.transaction() as conn:
            conn.execute(
                """
                INSERT INTO user_guild_roles (user_id, guild_id, role, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    role = excluded.role,
                    updated_at = excluded.updated_at
                """,
                (clean_uid, clean_gid, clean_role, _utc_now()),
            )
    except Exception:
        pass


def _get_user_guild_roles_map(user_id: str, default_main_role: str = "member") -> Dict[str, str]:
    clean_uid = str(user_id or "").strip()
    roles_map: Dict[str, str] = {}
    if not clean_uid:
        return roles_map
    _ensure_multi_session_table()
    try:
        with db_manager.transaction() as conn:
            rows = conn.execute(
                "SELECT guild_id, role FROM user_guild_roles WHERE user_id = ?",
                (clean_uid,),
            ).fetchall()
            for r in rows:
                rv = str(r["role"] or "member").lower()
                roles_map[str(r["guild_id"])] = rv if rv in ("admin", "dj", "member") else "member"
    except Exception:
        pass
<<<<<<< HEAD
=======
    main_gid = str(settings.main_guild_id or "1428666546942902294")
    if main_gid not in roles_map and default_main_role in ("admin", "dj", "member"):
        roles_map[main_gid] = default_main_role
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    return roles_map


def _resolve_role_for_guild(
    user_id: str,
    guild_id: str,
    default_main_role: str = "member",
    live_bot: Any = None,
) -> str:
<<<<<<< HEAD
    clean_gid = str(guild_id or "").strip()
    clean_uid = str(user_id or "").strip()

    # 1. Jika live Discord Bot aktif dan user adalah member asli di server tersebut, cek permission tertinggi real-time per-server
=======
    clean_gid = str(guild_id or settings.main_guild_id or "1428666546942902294").strip()
    clean_uid = str(user_id or "").strip()

    # 1. Jika live Discord Bot aktif dan user adalah member asli di server tersebut, cek permission real-time per-server
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    if live_bot is not None and clean_gid.isdigit() and clean_uid.isdigit():
        try:
            g_obj = live_bot.get_guild(int(clean_gid))
            m_obj = g_obj.get_member(int(clean_uid)) if g_obj else None
            if m_obj is not None:
                is_srv_admin = bool(
                    m_obj.guild_permissions.administrator
                    or getattr(m_obj.guild_permissions, "manage_guild", False)
                    or (g_obj and g_obj.owner_id == m_obj.id)
                )
                if is_srv_admin:
<<<<<<< HEAD
                    _set_user_guild_role(clean_uid, clean_gid, "admin")
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                    return "admin"
                dj_rid = ""
                if hasattr(live_bot, "_get_guild_dj_role_id"):
                    dj_rid = str(live_bot._get_guild_dj_role_id(clean_gid) or "")
                member_role_ids = [str(r.id) for r in getattr(m_obj, "roles", [])]
                member_role_names = [str(getattr(r, "name", "") or "").strip().lower() for r in getattr(m_obj, "roles", [])]
<<<<<<< HEAD
                has_dj_perm = bool(
                    getattr(m_obj.guild_permissions, "manage_channels", False)
                    or getattr(m_obj.guild_permissions, "mute_members", False)
                )
                if has_dj_perm or (dj_rid and dj_rid in member_role_ids) or any(
                    rn in ("dj", "athenaa dj", "role dj", "music dj") for rn in member_role_names
                ):
                    _set_user_guild_role(clean_uid, clean_gid, "dj")
                    return "dj"
                _set_user_guild_role(clean_uid, clean_gid, "member")
=======
                if (dj_rid and dj_rid in member_role_ids) or any(
                    rn in ("dj", "athenaa dj", "role dj", "music dj") for rn in member_role_names
                ):
                    return "dj"
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                return "member"
        except Exception:
            pass

    # 2. Cek mapping per-server di database user_guild_roles
    roles_map = _get_user_guild_roles_map(clean_uid, default_main_role=default_main_role)
<<<<<<< HEAD
    if clean_gid and clean_gid in roles_map:
        return roles_map[clean_gid]

    # 3. Jika user sudah memiliki catatan role di server lain namun belum di server ini, otomatis Member biasa
    if roles_map and clean_gid and clean_gid not in roles_map:
        return "member"

    return default_main_role if default_main_role in ("admin", "dj", "member") else "member"
=======
    if clean_gid in roles_map:
        return roles_map[clean_gid]

    # 3. Di server lain yang belum memiliki izin khusus, otomatis berstatus Member biasa
    if clean_gid == str(settings.main_guild_id or "1428666546942902294"):
        return default_main_role if default_main_role in ("admin", "dj", "member") else "member"
    return "member"
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006


def _build_valid_pdf_bytes(title: str, uploader: str, attachment_id: str) -> bytes:
    safe_title = (title or "Modul Akademik").replace("(", "[").replace(")", "]")
    safe_up = (uploader or "Aetheriaaa").replace("(", "[").replace(")", "]")
    stream_text = (
        "BT\n"
        "/F1 16 Tf\n"
        "50 760 Td\n"
        f"({safe_title}) Tj\n"
        "/F1 11 Tf\n"
        "0 -28 Td\n"
        f"(Diunggah oleh: {safe_up} | ID Lampiran: {attachment_id}) Tj\n"
        "0 -22 Td\n"
        "(Dokumen Modul Tervalidasi - Athenaa Academic Hub) Tj\n"
        "ET\n"
    ).encode("latin-1", errors="replace")
    s_len = len(stream_text)

    pdf_body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        + f"4 0 obj\n<< /Length {s_len} >>\nstream\n".encode("ascii")
        + stream_text
        + b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000229 00000 n \n"
        + f"{280 + s_len:010d} 00000 n \n".encode("ascii")
        + b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + f"{350 + s_len}\n%%EOF\n".encode("ascii")
    )
    return pdf_body


def _serialize_track_for_web(item: Any) -> Dict[str, Any]:
    raw_stream = str(getattr(item, "stream_url", "") or "")
    src_type = str(getattr(item, "source_type", "spotify_matched") or "spotify_matched")
    safe_web_stream = (
        raw_stream
        if (src_type == "radio" or (raw_stream and "googlevideo.com" not in raw_stream))
        else ""
    )
    return {
        "item_id": getattr(item, "item_id", ""),
        "guild_id": getattr(item, "guild_id", ""),
        "position": getattr(item, "position", 1),
        "title": getattr(item, "title", ""),
        "artist": getattr(item, "artist", ""),
        "album": getattr(item, "album", ""),
        "duration_sec": getattr(item, "duration_sec", 0),
        "source_type": src_type,
        "source_url": getattr(item, "source_url", ""),
        "stream_url": safe_web_stream,
        "thumbnail_url": getattr(item, "thumbnail_url", ""),
        "requester_id": getattr(item, "requester_id", ""),
        "requester_name": getattr(item, "requester_name", ""),
        "added_at": getattr(item, "added_at", ""),
        "is_autoplay": bool(getattr(item, "is_autoplay", False)),
    }


def _serialize_music_state(guild_id: str) -> Dict[str, Any]:
    st = queue_service.get_state(guild_id)
    return {
        "guild_id": st.guild_id,
        "voice_channel_id": st.voice_channel_id,
        "voice_channel_name": st.voice_channel_name,
        "host_user_id": st.host_user_id,
        "host_username": st.host_username,
        "is_playing": st.is_playing,
        "is_paused": st.is_paused,
        "position_sec": st.position_sec,
        "volume": st.volume,
        "loop_mode": st.loop_mode,
        "autoplay": st.autoplay,
        "mode_247": st.mode_247,
        "active_radio_name": st.active_radio_name,
        "current_track": _serialize_track_for_web(st.current_track) if st.current_track else None,
        "queue": [_serialize_track_for_web(item) for item in st.queue],
        "radios": VERIFIED_RADIO_STATIONS,
    }


def _issue_single_discord_session(
    user_id: str,
    username: str,
    discord_tag: str,
    role_label: str,
    is_owner: bool,
    has_dj_role: bool,
    is_admin: bool,
    guild_id: Optional[str] = None,
    guild_roles: Optional[Dict[str, str]] = None,
<<<<<<< HEAD
    avatar_url: str = "",
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
) -> Dict[str, Any]:
    """
    Menerbitkan token sesi untuk akun Discord dengan batas maksimal 5 perangkat/sesi aktif (MAX_SESSIONS_PER_USER = 5).
    Role disimpan spesifik per-server (guild_id), tanpa adanya role Owner global.
    """
    _ensure_multi_session_table()
<<<<<<< HEAD
    new_token = f"athenaa_sess_{user_id}_{secrets.token_hex(16)}"
=======
    new_token = f"athenaa_sess_{user_id}_{secrets.token_hex(12)}"
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    now_iso = _utc_now()
    oldest_evicted = False
    target_gid = str(guild_id or settings.main_guild_id or "1428666546942902294").strip()
    role_code = "admin" if is_admin else ("dj" if has_dj_role else "member")
<<<<<<< HEAD
    if target_gid:
        _set_user_guild_role(user_id, target_gid, role_code)
=======
    _set_user_guild_role(user_id, target_gid, role_code)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    if guild_roles:
        for gid_k, r_val in guild_roles.items():
            _set_user_guild_role(user_id, gid_k, r_val)

    with db_manager.transaction() as conn:
        legacy_row = conn.execute(
            "SELECT * FROM discord_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if legacy_row:
<<<<<<< HEAD
            legacy_avatar = str(legacy_row["avatar_url"]) if "avatar_url" in legacy_row.keys() else ""
            conn.execute(
                """
                INSERT OR IGNORE INTO discord_user_sessions (
                    session_token, user_id, username, discord_tag, avatar_url, role_label,
                    is_owner, has_dj_role, is_admin, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
=======
            conn.execute(
                """
                INSERT OR IGNORE INTO discord_user_sessions (
                    session_token, user_id, username, discord_tag, role_label,
                    is_owner, has_dj_role, is_admin, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                """,
                (
                    legacy_row["session_token"],
                    legacy_row["user_id"],
                    legacy_row["username"],
                    legacy_row["discord_tag"],
<<<<<<< HEAD
                    legacy_avatar,
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                    legacy_row["role_label"],
                    0,
                    int(legacy_row["has_dj_role"]),
                    int(legacy_row["is_admin"]),
                    legacy_row["created_at"],
                ),
            )

        conn.execute(
            """
            INSERT INTO discord_user_sessions (
<<<<<<< HEAD
                session_token, user_id, username, discord_tag, avatar_url, role_label,
                is_owner, has_dj_role, is_admin, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
=======
                session_token, user_id, username, discord_tag, role_label,
                is_owner, has_dj_role, is_admin, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            """,
            (
                new_token,
                user_id,
                username,
                discord_tag,
<<<<<<< HEAD
                avatar_url,
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                role_label,
                0,
                1 if has_dj_role else 0,
                1 if is_admin else 0,
                now_iso,
            ),
        )

        active_rows = conn.execute(
            """
            SELECT session_token FROM discord_user_sessions
            WHERE user_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (user_id,),
        ).fetchall()

        if len(active_rows) > MAX_SESSIONS_PER_USER:
            oldest_evicted = True
            excess_count = len(active_rows) - MAX_SESSIONS_PER_USER
            for old_row in active_rows[:excess_count]:
                conn.execute(
                    "DELETE FROM discord_user_sessions WHERE session_token = ?",
                    (old_row["session_token"],),
                )

        conn.execute(
            """
            INSERT INTO discord_sessions (
                user_id, session_token, username, discord_tag, role_label,
                is_owner, has_dj_role, is_admin, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                session_token = excluded.session_token,
                username = excluded.username,
                discord_tag = excluded.discord_tag,
                role_label = excluded.role_label,
                is_owner = 0,
                has_dj_role = excluded.has_dj_role,
                is_admin = excluded.is_admin,
                created_at = excluded.created_at
            """,
            (
                user_id,
                new_token,
                username,
                discord_tag,
                role_label,
                0,
                1 if has_dj_role else 0,
                1 if is_admin else 0,
                now_iso,
            ),
        )

        active_count = min(len(active_rows), MAX_SESSIONS_PER_USER)

    guild_roles_map = _get_user_guild_roles_map(user_id, default_main_role=role_code)
<<<<<<< HEAD
    if target_gid and target_gid not in guild_roles_map:
        guild_roles_map[target_gid] = role_code
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

    return {
        "session_token": new_token,
        "previous_token_revoked": oldest_evicted,
        "active_sessions_count": active_count,
        "max_sessions": MAX_SESSIONS_PER_USER,
        "user": {
            "id": user_id,
            "name": username,
            "discordTag": discord_tag,
<<<<<<< HEAD
            "avatarUrl": avatar_url,
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            "role": role_code,
            "roleLabel": role_label,
            "isOwner": False,
            "hasDjRole": has_dj_role,
            "isAdmin": is_admin,
            "guildRoles": guild_roles_map,
        },
    }


def _get_session_from_token(token: str, guild_id: Optional[str] = None, live_bot: Any = None) -> Optional[Dict[str, Any]]:
    clean = (token or "").strip()
    if not clean:
        return None
    _ensure_multi_session_table()
    with db_manager.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM discord_user_sessions WHERE session_token = ?",
            (clean,),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM discord_sessions WHERE session_token = ?",
                (clean,),
            ).fetchone()
    if not row:
        return None

    uid = str(row["user_id"])
<<<<<<< HEAD
    avatar_url = str(row["avatar_url"]) if "avatar_url" in row.keys() and row["avatar_url"] else ""
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    base_is_adm = bool(row["is_admin"])
    base_has_dj = bool(row["has_dj_role"]) or base_is_adm
    default_main_role = "admin" if base_is_adm else ("dj" if base_has_dj else "member")
    target_gid = str(guild_id or settings.main_guild_id or "1428666546942902294").strip()
    effective_role = _resolve_role_for_guild(
        user_id=uid,
        guild_id=target_gid,
        default_main_role=default_main_role,
        live_bot=live_bot,
    )
    is_adm = effective_role == "admin"
    has_dj = effective_role in ("admin", "dj")
    role_label = "Admin Server" if is_adm else ("Role DJ" if has_dj else "Member")
    guild_roles_map = _get_user_guild_roles_map(uid, default_main_role=default_main_role)
<<<<<<< HEAD
    if live_bot is not None and uid.isdigit():
        try:
            for g in getattr(live_bot, "guilds", []) or []:
                gid_s = str(getattr(g, "id", "") or "").strip()
                if gid_s:
                    guild_roles_map[gid_s] = _resolve_role_for_guild(
                        user_id=uid,
                        guild_id=gid_s,
                        default_main_role=default_main_role,
                        live_bot=live_bot,
                    )
        except Exception:
            pass
    if target_gid:
        guild_roles_map[target_gid] = effective_role
=======
    guild_roles_map[target_gid] = effective_role
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

    return {
        "session_token": row["session_token"],
        "user": {
            "id": uid,
            "name": row["username"],
            "discordTag": row["discord_tag"],
<<<<<<< HEAD
            "avatarUrl": avatar_url,
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            "role": effective_role,
            "roleLabel": role_label,
            "isOwner": False,
            "hasDjRole": has_dj,
            "isAdmin": is_adm,
            "guildRoles": guild_roles_map,
        },
    }


def get_system_metrics(actor_id: str = "", is_admin: bool = True) -> Dict[str, Any]:
    if not is_admin:
        raise PermissionError("Akses ditolak: Hanya Admin Server yang diizinkan mengakses Admin Hub.")

    ram_mb = 0.0
    cpu_percent = 0.0
    try:
        import psutil  # type: ignore

        proc = psutil.Process(os.getpid())
        ram_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
        cpu_percent = round(proc.cpu_percent(interval=0.05), 1)
    except ImportError:
        status_file = Path("/proc/self/status")
        if status_file.exists():
            for line in status_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    ram_mb = round(kb / 1024.0, 2)
                    break

    db_size_bytes = settings.sqlite_path.stat().st_size if settings.sqlite_path.exists() else 0
    backups = []
    if settings.backups_dir.exists():
        for f in sorted(settings.backups_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.suffix in (".enc", ".gz"):
                st = f.stat()
                backups.append(
                    {
                        "filename": f.name,
                        "size_bytes": st.st_size,
                        "created_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                    }
                )

    return {
        "ram_rss_mb": ram_mb,
        "heap_used_mb": ram_mb,
        "cpu_load_1m": cpu_percent,
        "ram_mb": ram_mb,
        "cpu_percent": cpu_percent,
        "uptime_seconds": int(time.time() - START_TIME),
        "database_size_kb": round(db_size_bytes / 1024.0, 2),
        "python_version": f"Python {sys.version.split()[0]} + FFmpeg",
        "discord_configured": bool(settings.discord_token),
        "backups": backups,
        "scope_note": "Metrik diukur dari proses/kontainer aplikasi saat ini (bukan keseluruhan node fisik).",
    }


def create_fastapi_app():
    """Membangun aplikasi FastAPI lengkap + WebSocket + Static SPA untuk Pterodactyl."""
    if not FASTAPI_AVAILABLE:
        return None

    app = FastAPI(title="Athenaa Discord Bot & Web Dashboard API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    ws_clients: Set[WebSocket] = set()
    app_loop_ref: List[asyncio.AbstractEventLoop] = []

    def _list_synchronized_guilds() -> List[Dict[str, Any]]:
        live_bot = getattr(app.state, "bot", None)
        if live_bot is not None:
            try:
                for g in getattr(live_bot, "guilds", []) or []:
                    gid = str(getattr(g, "id", "") or "").strip()
                    gname = str(getattr(g, "name", "") or "").strip()
                    if gid:
                        queue_service.register_active_guild(gid, gname or f"Server {gid}")
            except Exception:
                pass

        for gid, gname in list(queue_service.active_guilds.items()):
            try:
                academy_service.ensure_guild_exists(gid, gname)
            except Exception:
                pass

        with db_manager.transaction() as conn:
            rows = conn.execute(
                """
                SELECT * FROM guild_settings
<<<<<<< HEAD
                ORDER BY guild_name ASC
                """
=======
                ORDER BY CASE WHEN guild_id = ? THEN 0 ELSE 1 END, guild_name ASC
                """,
                (str(settings.main_guild_id or ""),),
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            st = queue_service.get_state(str(d["guild_id"]))
            d["autoplay"] = 1 if st.autoplay else 0
            d["mode_247"] = 1 if st.mode_247 else 0
            result.append(d)
        return result

    async def _broadcast_guild_state(guild_id: str) -> None:
        if not ws_clients:
            return
        payload = json.dumps(
            {
                "type": "MUSIC_STATE_UPDATE",
                "guild_id": guild_id,
                "state": _serialize_music_state(guild_id),
                "guilds": _list_synchronized_guilds(),
            }
        )
        dead: List[WebSocket] = []
        for ws in list(ws_clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for d in dead:
            ws_clients.discard(d)

    app.state.broadcast_guild_state = _broadcast_guild_state

    def _on_queue_change(guild_id: str, _state: GuildQueueState, _event_type: str) -> None:
        if _event_type == "voice_sync":
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_broadcast_guild_state(guild_id))
        except RuntimeError:
            if app_loop_ref and app_loop_ref[0].is_running():
                asyncio.run_coroutine_threadsafe(_broadcast_guild_state(guild_id), app_loop_ref[0])

    queue_service.register_listener(_on_queue_change)

    @app.on_event("startup")
    async def _start_playback_clock() -> None:
        app_loop_ref.clear()
        app_loop_ref.append(asyncio.get_running_loop())

        async def _clock_loop() -> None:
            while True:
                await asyncio.sleep(1.0)
                if getattr(queue_service, "voice_bot_active", False):
                    continue
                for gid, st in list(queue_service._states.items()):
                    if st.is_playing and not st.is_paused and st.current_track:
                        st.position_sec += 1
                        if (
                            st.current_track.source_type != "radio"
                            and st.current_track.duration_sec > 0
                            and st.position_sec >= st.current_track.duration_sec + 3
                        ):
                            queue_service.advance_track(gid)
                        await _broadcast_guild_state(gid)

        asyncio.create_task(_clock_loop())

    def _extract_session(request: Request, guild_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_gid = (
            guild_id
            or request.path_params.get("guild_id")
            or request.query_params.get("guild_id")
            or request.headers.get("X-Guild-Id")
            or settings.main_guild_id
            or ""
        ).strip()
        auth_header = request.headers.get("Authorization", "")
        bearer = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
        q_tok = request.query_params.get("session_token", "").strip()
        cookie_tok = request.cookies.get("athenaa_session_token", "").strip()
        explicit_tok = bearer or q_tok or cookie_tok
<<<<<<< HEAD
        if not explicit_tok:
            return None
        live_bot = getattr(app.state, "bot", None)
        return _get_session_from_token(explicit_tok, guild_id=target_gid, live_bot=live_bot)
=======
        live_bot = getattr(app.state, "bot", None)
        sess = _get_session_from_token(explicit_tok, guild_id=target_gid, live_bot=live_bot)
        role_override = request.headers.get("X-Actor-Role", "").strip().lower()

        if sess and explicit_tok:
            guild_roles_map = sess["user"].get("guildRoles") or {}
            # Jika user sudah memiliki mapping role per-server, patuhi role pada server (target_gid) tersebut
            if guild_roles_map and target_gid:
                return sess

        if role_override in ("admin", "dj", "member"):
            base_user = sess["user"] if sess else {
                "id": "844174494099701780" if role_override == "admin" else ("user-dj-02" if role_override == "dj" else "user-member-03"),
                "name": "Admin Server" if role_override == "admin" else ("Role DJ" if role_override == "dj" else "Member"),
                "discordTag": "@admin" if role_override == "admin" else ("@dj_nyolbar" if role_override == "dj" else "@member_kampus"),
                "guildRoles": {target_gid: role_override} if target_gid else {},
            }
            is_adm = role_override == "admin"
            is_dj = role_override in ("admin", "dj")
            return {
                "session_token": sess["session_token"] if sess else f"role_{role_override}",
                "user": {
                    **base_user,
                    "role": role_override,
                    "roleLabel": "Admin Server" if is_adm else ("Role DJ" if is_dj else "Member"),
                    "isAdmin": is_adm,
                    "hasDjRole": is_dj,
                    "isOwner": False,
                },
            }
        return sess
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

    @app.get("/health")
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "uptime_seconds": int(time.time() - START_TIME)}

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        ws_clients.add(ws)
        try:
<<<<<<< HEAD
            synced_guilds = _list_synchronized_guilds()
            initial_gid = str(synced_guilds[0]["guild_id"]) if synced_guilds else str(settings.main_guild_id or "1428666546942902294")
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            await ws.send_text(
                json.dumps(
                    {
                        "type": "MUSIC_STATE_UPDATE",
<<<<<<< HEAD
                        "guild_id": initial_gid,
                        "state": _serialize_music_state(initial_gid),
                        "guilds": synced_guilds,
=======
                        "guild_id": settings.main_guild_id,
                        "state": _serialize_music_state(settings.main_guild_id),
                        "guilds": _list_synchronized_guilds(),
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                    }
                )
            )
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            ws_clients.discard(ws)
        except Exception:
            ws_clients.discard(ws)

    # =========================================================================
    # Multi-Device Discord Authentication & OAuth2 Routes (Maks. 5 Sesi/User)
    # =========================================================================
    auth_rate_limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60)

    def _check_auth_rate_limit(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        if not auth_rate_limiter.allow(f"auth:{client_ip}"):
            raise HTTPException(status_code=429, detail="Terlalu banyak percobaan login. Coba lagi nanti.")

<<<<<<< HEAD
    def _resolve_dynamic_redirect_uri(request: Request) -> str:
        configured = (settings.discord_redirect_uri or "").strip()
        if "your-domain.com" in configured.lower() or "example.com" in configured.lower():
            configured = ""
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
        if host and ("localhost" not in host and "127.0.0.1" not in host):
            if not configured or "localhost" in configured or "127.0.0.1" in configured:
                return f"{proto}://{host}/auth/callback"
        if configured:
            return configured
        if host:
            return f"{proto}://{host}/auth/callback"
        return "http://localhost:10031/auth/callback"

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    @app.get("/api/auth/session")
    async def api_auth_session(request: Request, guild_id: str = Query("")):
        _check_auth_rate_limit(request)
        target_gid = (guild_id or request.headers.get("X-Guild-Id") or settings.main_guild_id or "").strip()
        sess = _extract_session(request, guild_id=target_gid)
<<<<<<< HEAD
        oauth_ready = bool(settings.discord_client_id and settings.discord_client_id.isdigit() and settings.discord_client_secret)
=======
        oauth_ready = bool(settings.discord_client_id and settings.discord_client_secret)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        if sess:
            return {
                "authenticated": True,
                "session_token": sess["session_token"],
                "user": sess["user"],
                "max_sessions": MAX_SESSIONS_PER_USER,
                "oauth_configured": oauth_ready,
            }
<<<<<<< HEAD
        return {
            "authenticated": False,
            "error": "Wajib login menggunakan akun Discord untuk mengakses Athenaa Web Player.",
=======
        with db_manager.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM discord_user_sessions ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM discord_sessions ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
        if row:
            live_bot = getattr(app.state, "bot", None)
            base_is_adm = bool(row["is_admin"])
            base_has_dj = bool(row["has_dj_role"]) or base_is_adm
            default_main_role = "admin" if base_is_adm else ("dj" if base_has_dj else "member")
            eff_role = _resolve_role_for_guild(
                user_id=row["user_id"],
                guild_id=target_gid,
                default_main_role=default_main_role,
                live_bot=live_bot,
            )
            is_adm = eff_role == "admin"
            has_dj = eff_role in ("admin", "dj")
            role_label = "Admin Server" if is_adm else ("Role DJ" if has_dj else "Member")
            guild_roles_map = _get_user_guild_roles_map(row["user_id"], default_main_role=default_main_role)
            if target_gid:
                guild_roles_map[target_gid] = eff_role
            return {
                "authenticated": True,
                "session_token": row["session_token"],
                "user": {
                    "id": row["user_id"],
                    "name": row["username"],
                    "discordTag": row["discord_tag"],
                    "role": eff_role,
                    "roleLabel": role_label,
                    "isOwner": False,
                    "hasDjRole": has_dj,
                    "isAdmin": is_adm,
                    "guildRoles": guild_roles_map,
                },
                "max_sessions": MAX_SESSIONS_PER_USER,
                "oauth_configured": oauth_ready,
            }
        return {
            "authenticated": False,
            "error": "Masuk dengan akun Discord atau pilih role server untuk mengakses panel.",
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            "oauth_configured": oauth_ready,
        }

    @app.post("/api/auth/login")
    async def api_auth_login(request: Request):
        _check_auth_rate_limit(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        role_req = str(body.get("role") or "admin").strip().lower()
        if role_req not in ("admin", "dj", "member"):
            role_req = "member"
        target_gid = str(body.get("guild_id") or request.headers.get("X-Guild-Id") or settings.main_guild_id or "").strip()
        uid = str(body.get("user_id") or ("844174494099701780" if role_req == "admin" else f"user-{role_req}-01"))
<<<<<<< HEAD
        uname = str(body.get("username") or ("Aetheriaaa" if role_req == "admin" else ("DJ NyolBar" if role_req == "dj" else "Member Server")))
        utag = str(body.get("discord_tag") or f"@{uname.lower().replace(' ', '_')}")
        avatar_url = str(body.get("avatar_url") or "")
        live_bot = getattr(app.state, "bot", None)
        eff_role = _resolve_role_for_guild(
            user_id=uid,
            guild_id=target_gid,
            default_main_role=role_req,
            live_bot=live_bot,
        )
        is_adm = eff_role == "admin"
        has_dj = eff_role in ("admin", "dj")
=======
        uname = str(body.get("username") or ("Admin Server" if role_req == "admin" else ("Role DJ" if role_req == "dj" else "Member")))
        utag = str(body.get("discord_tag") or f"@{uname.lower().replace(' ', '_')}")
        is_adm = role_req == "admin"
        has_dj = role_req in ("admin", "dj")
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        role_label = "Admin Server" if is_adm else ("Role DJ" if has_dj else "Member")
        issued = _issue_single_discord_session(
            user_id=uid,
            username=uname,
            discord_tag=utag,
            role_label=role_label,
            is_owner=False,
            has_dj_role=has_dj,
            is_admin=is_adm,
            guild_id=target_gid,
<<<<<<< HEAD
            avatar_url=avatar_url,
        )
        resp = JSONResponse(
            {
                "authenticated": True,
                "session_token": issued["session_token"],
                "user": {
                    **issued["user"],
                    "role": eff_role,
                    "isOwner": False,
                },
            }
        )
        resp.set_cookie(
            key="athenaa_session_token",
            value=issued["session_token"],
            max_age=604800,
            path="/",
            httponly=True,
            samesite="lax",
        )
        return resp

    @app.post("/api/auth/logout")
    async def api_auth_logout(request: Request):
        auth_header = request.headers.get("Authorization", "")
        bearer = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
        q_tok = request.query_params.get("session_token", "").strip()
        cookie_tok = request.cookies.get("athenaa_session_token", "").strip()
        tok = bearer or q_tok or cookie_tok
        if tok:
            with db_manager.transaction() as conn:
                conn.execute("DELETE FROM discord_user_sessions WHERE session_token = ?", (tok,))
                conn.execute("DELETE FROM discord_sessions WHERE session_token = ?", (tok,))
        resp = JSONResponse({"ok": True, "authenticated": False})
=======
        )
        return {
            "authenticated": True,
            "session_token": issued["session_token"],
            "user": {
                **issued["user"],
                "role": role_req,
                "isOwner": False,
            },
        }

    @app.post("/api/auth/logout")
    async def api_auth_logout(request: Request):
        sess = _extract_session(request)
        if sess:
            tok = sess["session_token"]
            uid = sess["user"]["id"]
            with db_manager.transaction() as conn:
                conn.execute("DELETE FROM discord_user_sessions WHERE session_token = ?", (tok,))
                conn.execute("DELETE FROM discord_sessions WHERE session_token = ?", (tok,))
                remaining = conn.execute(
                    """
                    SELECT * FROM discord_user_sessions
                    WHERE user_id = ?
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT 1
                    """,
                    (uid,),
                ).fetchone()
                if remaining:
                    conn.execute(
                        """
                        INSERT INTO discord_sessions (
                            user_id, session_token, username, discord_tag, role_label,
                            is_owner, has_dj_role, is_admin, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            session_token = excluded.session_token,
                            created_at = excluded.created_at
                        """,
                        (
                            remaining["user_id"],
                            remaining["session_token"],
                            remaining["username"],
                            remaining["discord_tag"],
                            remaining["role_label"],
                            int(remaining["is_owner"]),
                            int(remaining["has_dj_role"]),
                            int(remaining["is_admin"]),
                            remaining["created_at"],
                        ),
                    )
        resp = JSONResponse({"ok": True})
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        resp.delete_cookie("athenaa_session_token", path="/")
        return resp

    @app.get("/api/auth/discord/url")
<<<<<<< HEAD
    async def api_discord_oauth_url(request: Request):
        redirect_uri = _resolve_dynamic_redirect_uri(request)
        if not settings.discord_client_id or not settings.discord_client_id.isdigit() or not settings.discord_client_secret:
            return JSONResponse(
                status_code=200,
                content={
                    "oauth_configured": False,
                    "url": None,
                    "redirect_uri": redirectUri if "redirectUri" in locals() else redirect_uri,
                    "error": "DISCORD_CLIENT_ID & DISCORD_CLIENT_SECRET belum diisi pada file .env di Pterodactyl.",
                },
            )
        oauth_state = generate_oauth_state(settings.encryption_secret)
        params = urllib.parse.urlencode(
            {
                "client_id": settings.discord_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "identify guilds",
                "state": oauth_state,
=======
    async def api_discord_oauth_url():
        if not settings.discord_client_id:
            return JSONResponse(
                status_code=400,
                content={
                    "oauth_configured": False,
                    "redirect_uri": settings.discord_redirect_uri,
                    "error": "DISCORD_CLIENT_ID belum diisi pada file .env di Pterodactyl.",
                },
            )
        params = urllib.parse.urlencode(
            {
                "client_id": settings.discord_client_id,
                "redirect_uri": settings.discord_redirect_uri,
                "response_type": "code",
                "scope": "identify guilds",
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                "prompt": "consent",
            }
        )
        return {
            "oauth_configured": True,
<<<<<<< HEAD
            "redirect_uri": redirect_uri,
            "state": oauth_state,
=======
            "redirect_uri": settings.discord_redirect_uri,
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            "url": f"https://discord.com/oauth2/authorize?{params}",
        }

    @app.get("/api/auth/discord/invite")
    @app.get("/invite")
    async def api_discord_bot_invite(request: Request, mode: str = Query("admin")):
        cid = (settings.discord_client_id or "").strip()
        if not cid:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "DISCORD_CLIENT_ID belum diisi pada file .env. Wajib di-set untuk invite URL.",
                },
            )

        perms = "8" if mode == "admin" else "36793408"
        invite_url = (
            f"https://discord.com/oauth2/authorize?client_id={urllib.parse.quote(cid)}"
            f"&permissions={perms}&scope=bot%20applications.commands"
        )
        if request.url.path == "/invite" or request.query_params.get("redirect") == "1":
            return RedirectResponse(url=invite_url)

        return {
            "client_id": cid,
            "invite_url_admin": f"https://discord.com/oauth2/authorize?client_id={urllib.parse.quote(cid)}&permissions=8&scope=bot%20applications.commands",
            "invite_url_standard": f"https://discord.com/oauth2/authorize?client_id={urllib.parse.quote(cid)}&permissions=36793408&scope=bot%20applications.commands",
            "url": invite_url,
        }

    @app.get("/auth/callback")
    @app.get("/auth/callback/")
<<<<<<< HEAD
    @app.get("/auth/discord/callback")
    @app.get("/api/auth/discord/callback")
    async def discord_oauth_callback(request: Request, code: str = Query(""), state: str = Query("")):
=======
    async def discord_oauth_callback(request: Request, code: str = Query("")):
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        _check_auth_rate_limit(request)
        if not code or not settings.discord_client_id or not settings.discord_client_secret:
            return HTMLResponse("<h3>Parameter OAuth2 Discord tidak lengkap.</h3>", status_code=400)

<<<<<<< HEAD
        if state and not verify_oauth_state(state, settings.encryption_secret):
            return HTMLResponse("<h3>State OAuth2 tidak valid atau telah kedaluwarsa (Proteksi Anti-CSRF). Silakan ulangi login.</h3>", status_code=400)

        redirect_uri = _resolve_dynamic_redirect_uri(request)
        access_token = ""
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        try:
            data = urllib.parse.urlencode(
                {
                    "client_id": settings.discord_client_id,
                    "client_secret": settings.discord_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
<<<<<<< HEAD
                    "redirect_uri": redirect_uri,
=======
                    "redirect_uri": settings.discord_redirect_uri,
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                "https://discord.com/api/oauth2/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "AthenaaBot/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                token_payload = json.loads(resp.read().decode("utf-8"))

<<<<<<< HEAD
            access_token = str(token_payload.get("access_token", "") or "")
=======
            access_token = token_payload.get("access_token", "")
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            user_req = urllib.request.Request(
                "https://discord.com/api/users/@me",
                headers={"Authorization": f"Bearer {access_token}", "User-Agent": "AthenaaBot/1.0"},
            )
            with urllib.request.urlopen(user_req, timeout=10.0) as uresp:
                user_data = json.loads(uresp.read().decode("utf-8"))

            uid = str(user_data.get("id", ""))
            uname = str(user_data.get("global_name") or user_data.get("username") or "DiscordUser")
            raw_username = str(user_data.get("username") or uname)
            disc = str(user_data.get("discriminator") or "0")
            utag = f"@{raw_username}" if disc == "0" else f"{raw_username}#{disc}"
<<<<<<< HEAD
            avatar_hash = str(user_data.get("avatar") or "").strip()
            if avatar_hash and uid:
                avatar_url = f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.png?size=128"
            else:
                default_idx = (int(uid) >> 22) % 6 if uid.isdigit() else 0
                avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_idx}.png"
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

            is_admin = False
            has_dj_role = False
            role_label = "Member"
            guild_roles_record: Dict[str, str] = {}
<<<<<<< HEAD
            live_bot = getattr(app.state, "bot", None)
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

            try:
                guilds_req = urllib.request.Request(
                    "https://discord.com/api/users/@me/guilds",
                    headers={"Authorization": f"Bearer {access_token}", "User-Agent": "AthenaaBot/1.0"},
                )
                with urllib.request.urlopen(guilds_req, timeout=10.0) as gresp:
                    guilds_data = json.loads(gresp.read().decode("utf-8"))

                for guild in guilds_data:
                    gid_str = str(guild.get("id", "")).strip()
                    if not gid_str:
                        continue
                    perms_int = int(guild.get("permissions", "0") or "0")
                    guild_is_adm = bool(guild.get("owner")) or bool(perms_int & 0x8) or bool(perms_int & 0x20)
<<<<<<< HEAD
                    guild_is_dj = bool(perms_int & 0x10) or bool(perms_int & 0x400000)
                    guild_role = "admin" if guild_is_adm else ("dj" if guild_is_dj else "member")

                    if live_bot is not None and gid_str.isdigit():
                        resolved_live = _resolve_role_for_guild(uid, gid_str, default_main_role=guild_role, live_bot=live_bot)
                        if resolved_live in ("admin", "dj"):
                            guild_role = resolved_live

                    guild_roles_record[gid_str] = guild_role
                    _set_user_guild_role(uid, gid_str, guild_role)
            except Exception:
                pass

            # Jika live_bot aktif, sinkronkan juga semua guild tempat bot berada
            if live_bot is not None and uid.isdigit():
                try:
                    for g in getattr(live_bot, "guilds", []) or []:
                        gid_s = str(getattr(g, "id", "") or "").strip()
                        if gid_s:
                            r_live = _resolve_role_for_guild(
                                uid,
                                gid_s,
                                default_main_role=guild_roles_record.get(gid_s, "member"),
                                live_bot=live_bot,
                            )
                            guild_roles_record[gid_s] = r_live
                            _set_user_guild_role(uid, gid_s, r_live)
                except Exception:
                    pass

            synced_guilds = _list_synchronized_guilds()
            primary_gid = (
                str(synced_guilds[0]["guild_id"])
                if synced_guilds
                else (next(iter(guild_roles_record.keys()), "") or str(settings.main_guild_id or "1428666546942902294"))
            )
            primary_role = guild_roles_record.get(primary_gid, "member")
            is_admin = primary_role == "admin"
            has_dj_role = primary_role in ("admin", "dj")
            role_label = "Admin Server" if is_admin else ("Role DJ" if has_dj_role else "Member")

=======
                    guild_role = "admin" if guild_is_adm else "member"

                    if not guild_is_adm and settings.main_guild_id and gid_str == str(settings.main_guild_id):
                        try:
                            member_req = urllib.request.Request(
                                f"https://discord.com/api/users/@me/guilds/{settings.main_guild_id}/member",
                                headers={"Authorization": f"Bearer {access_token}", "User-Agent": "AthenaaBot/1.0"},
                            )
                            with urllib.request.urlopen(member_req, timeout=10.0) as mresp:
                                member_data = json.loads(mresp.read().decode("utf-8"))
                            user_roles = member_data.get("roles", [])
                            if settings.dj_role_id and settings.dj_role_id in user_roles:
                                guild_role = "dj"
                        except Exception:
                            pass

                    guild_roles_record[gid_str] = guild_role
                    _set_user_guild_role(uid, gid_str, guild_role)

                    if not settings.main_guild_id or gid_str == str(settings.main_guild_id):
                        if guild_role == "admin":
                            is_admin = True
                            has_dj_role = True
                            role_label = "Admin Server"
                        elif guild_role == "dj":
                            has_dj_role = True
                            role_label = "Role DJ"
            except Exception:
                pass

>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            issued = _issue_single_discord_session(
                user_id=uid,
                username=uname,
                discord_tag=utag,
                role_label=role_label,
                is_owner=False,
                has_dj_role=has_dj_role,
                is_admin=is_admin,
<<<<<<< HEAD
                guild_id=primary_gid,
                guild_roles=guild_roles_record,
                avatar_url=avatar_url,
=======
                guild_id=settings.main_guild_id,
                guild_roles=guild_roles_record,
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            )

            token_str = issued["session_token"]
            msg_json = json.dumps(
                {
                    "type": "OAUTH_AUTH_SUCCESS",
                    "session_token": token_str,
                    "user": issued["user"],
                }
            )
            redirect_target = f"/?session_token={urllib.parse.quote(token_str)}"
            html = f"""<!doctype html>
<html lang="id">
<head><meta charset="utf-8"><title>Login Berhasil — Athenaa</title></head>
<body style="background:#121212;color:#fff;font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;margin:0;gap:12px;">
<script>
  (function() {{
    var payload = {msg_json};
    var token = {json.dumps(token_str)};
    var redirectUrl = {json.dumps(redirect_target)};
    try {{
      window.localStorage.setItem('athenaa_session_token', token);
      window.localStorage.setItem('athenaa_oauth_user', JSON.stringify(payload.user));
    }} catch (e) {{}}
    try {{
      if (typeof BroadcastChannel !== 'undefined') {{
        var bc = new BroadcastChannel('athenaa_oauth');
        bc.postMessage(payload);
      }}
    }} catch (e) {{}}
    if (window.opener && !window.opener.closed) {{
      try {{
        window.opener.postMessage(payload, '*');
      }} catch (e) {{}}
      setTimeout(function() {{
        window.close();
      }}, 250);
      setTimeout(function() {{
        window.location.replace(redirectUrl);
      }}, 700);
    }} else {{
      window.location.replace(redirectUrl);
    }}
  }})();
</script>
<div style="width:44px;height:44px;border-radius:9999px;background:#DC95FF;color:#000;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:20px;">A</div>
<p style="margin:0;font-size:15px;">Login berhasil sebagai <strong>{uname}</strong> ({utag}).</p>
<a href="{redirect_target}" style="color:#DC95FF;font-size:13px;font-weight:700;">Klik di sini jika halaman tidak berpindah otomatis</a>
</body>
</html>"""
            response = HTMLResponse(html)
            response.set_cookie(
                key="athenaa_session_token",
                value=token_str,
                max_age=604800,
                path="/",
<<<<<<< HEAD
                httponly=True,
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                samesite="lax",
            )
            return response
        except Exception as exc:
            return HTMLResponse(f"<h3>Gagal memproses OAuth2 Discord: {exc}</h3>", status_code=500)
<<<<<<< HEAD
        finally:
            # Keamanan Maksimal: Cabut (Revoke) access_token Discord segera setelah membaca profil & daftar server
            # sehingga tidak ada satupun token OAuth2 Discord yang tersimpan di server atau dapat disalahgunakan.
            if access_token and settings.discord_client_id and settings.discord_client_secret:
                try:
                    rev_data = urllib.parse.urlencode(
                        {
                            "client_id": settings.discord_client_id,
                            "client_secret": settings.discord_client_secret,
                            "token": access_token,
                        }
                    ).encode("utf-8")
                    rev_req = urllib.request.Request(
                        "https://discord.com/api/oauth2/token/revoke",
                        data=rev_data,
                        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "AthenaaBot/1.0"},
                        method="POST",
                    )
                    with urllib.request.urlopen(rev_req, timeout=4.0):
                        pass
                except Exception:
                    pass
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

    # =========================================================================
    # Guilds & Music Endpoints (25-Item Single Dropdown & Direct Playlist Play)
    # =========================================================================
    @app.get("/api/guilds")
    async def api_guilds():
        return {"guilds": _list_synchronized_guilds()}

    @app.get("/api/guilds/{guild_id}/settings")
    async def api_guild_settings(guild_id: str):
        with db_manager.transaction() as conn:
            row = conn.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Server tidak ditemukan.")
        d = dict(row)
        st = queue_service.get_state(guild_id)
        d["autoplay"] = 1 if st.autoplay else 0
        d["mode_247"] = 1 if st.mode_247 else 0
        return {"settings": d}

    @app.patch("/api/guilds/{guild_id}/settings")
    async def api_update_guild_settings(guild_id: str, request: Request):
        body = await request.json()
        now_iso = _utc_now()
        st = queue_service.get_state(guild_id)
        if "autoplay" in body and body["autoplay"] is not None:
            st.autoplay = bool(int(body["autoplay"]) if isinstance(body["autoplay"], (int, str)) else body["autoplay"])
        if "mode_247" in body and body["mode_247"] is not None:
            st.mode_247 = bool(int(body["mode_247"]) if isinstance(body["mode_247"], (int, str)) else body["mode_247"])
        if "default_volume" in body and body["default_volume"] is not None:
            st.volume = max(1, min(100, int(body["default_volume"])))

        with db_manager.transaction() as conn:
            conn.execute(
                """
                UPDATE guild_settings
                SET music_channel_id = COALESCE(?, music_channel_id),
                    task_channel_id = COALESCE(?, task_channel_id),
                    dj_role_id = COALESCE(?, dj_role_id),
                    moodle_ics_url_encrypted = COALESCE(?, moodle_ics_url_encrypted),
                    reminder_days_before = COALESCE(?, reminder_days_before),
                    timezone = COALESCE(?, timezone),
                    exp_cooldown_seconds = COALESCE(?, exp_cooldown_seconds),
                    autoplay = ?,
                    mode_247 = ?,
                    default_volume = ?,
                    updated_at = ?
                WHERE guild_id = ?
                """,
                (
                    body.get("music_channel_id"),
                    body.get("task_channel_id"),
                    body.get("dj_role_id"),
                    body.get("moodle_ics_url_encrypted"),
                    body.get("reminder_days_before"),
                    body.get("timezone"),
                    body.get("exp_cooldown_seconds"),
                    1 if st.autoplay else 0,
                    1 if st.mode_247 else 0,
                    st.volume,
                    now_iso,
                    guild_id,
                ),
            )
            row = conn.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
        await _broadcast_guild_state(guild_id)
        return {"settings": dict(row) if row else {}}

    @app.get("/api/music/search")
    async def api_search_music(q: str = Query("", max_length=500)):
        cleaned_q = (q or "").strip()

        if cleaned_q:
            try:
                kind, _ = classify_music_input(cleaned_q)
                if kind in ("spotify_playlist", "spotify_album", "youtube_playlist"):
                    pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, cleaned_q, 50)
                    pl_tracks = pl_data.get("tracks") or []
                    is_yt_pl = kind == "youtube_playlist"
                    pl_name = str(
                        pl_data.get("playlist_name")
                        or ("YouTube Playlist" if is_yt_pl else "Spotify Playlist")
                    )
                    pl_thumb = str(
                        pl_data.get("thumbnail_url")
                        or (pl_tracks[0].thumbnail_url if pl_tracks else "")
                    )
                    total_dur = sum(int(t.duration_sec or 180) for t in pl_tracks)
                    dropdown_items: List[Dict[str, Any]] = [
                        {
                            "title": f"🎶 [PLAYLIST] {pl_name}",
                            "artist": f"Putar Langsung Semua ({len(pl_tracks)} Lagu)",
                            "album": "YouTube Playlist" if is_yt_pl else "Spotify Playlist",
                            "duration_sec": total_dur,
                            "source_type": kind,
                            "source_url": cleaned_q,
                            "stream_url": "",
                            "thumbnail_url": pl_thumb,
                            "notice": "Klik Putar / +Antrean atau tekan Enter untuk memutar seluruh playlist",
                        }
                    ]
                    for tr in pl_tracks[:24]:
                        dropdown_items.append(asdict(tr))
                    return {"results": dropdown_items[:25]}
            except Exception:
                pass

        tracks = await asyncio.to_thread(search_songs_with_singer, cleaned_q, 25)
        return {"results": [asdict(t) for t in tracks[:25]]}

    @app.get("/api/music/stream")
    async def api_music_stream(
        title: str = Query(""),
        artist: str = Query(""),
        source_url: str = Query(""),
    ):
        resolved = await asyncio.to_thread(resolve_browser_preview_stream, title, artist, source_url)
        return resolved

    @app.post("/api/music/resolve")
    async def api_resolve_music(request: Request):
        body = await request.json()
        raw_input = str(body.get("input") or body.get("query") or "").strip()
        kind, _ = classify_music_input(raw_input)
        if kind in ("spotify_playlist", "spotify_album", "youtube_playlist"):
            pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, raw_input, 50)
            tracks = pl_data.get("tracks") or []
            if not tracks:
                raise HTTPException(status_code=404, detail="Lagu dalam playlist tidak ditemukan.")
            return {
                "is_playlist": True,
                "playlist_name": pl_data.get("playlist_name"),
                "track": asdict(tracks[0]),
                "tracks": [asdict(t) for t in tracks],
            }
        if kind == "spotify_track":
            cand = await asyncio.to_thread(resolve_spotify_link, raw_input)
            return {"track": asdict(cand)}
        tracks = await asyncio.to_thread(search_songs_with_singer, raw_input, 1)
        if not tracks:
            raise HTTPException(status_code=404, detail="Lagu tidak ditemukan.")
        return {"track": asdict(tracks[0])}

    @app.get("/api/music/lyrics")
    async def api_lyrics(title: str = Query(...), artist: str = Query("")):
        res = await asyncio.to_thread(lyrics_service.get_lyrics, title, artist)
        is_found = getattr(res, "found", res.status in ("synced", "plain"))
        return {
            "found": is_found,
            "status": res.status,
            "track_name": res.track_name,
            "artist_name": res.artist_name,
            "synced_lyrics": "\n".join(
                f"[{int(l.time_sec // 60):02d}:{l.time_sec % 60:05.2f}] {l.text}" for l in res.synced_lines
            ),
            "plain_lyrics": res.plain_lyrics,
            "synced_lines": [{"time_sec": l.time_sec, "timeSec": l.time_sec, "text": l.text} for l in res.synced_lines],
            "message": res.message,
        }

    @app.get("/api/guilds/{guild_id}/music/state")
    async def api_music_state(guild_id: str):
        validate_snowflake_param("guild_id", guild_id)
        return _serialize_music_state(guild_id)

<<<<<<< HEAD
    def _require_admin(request: Request) -> None:
        target_gid = (
            request.path_params.get("guild_id")
            or request.query_params.get("guild_id")
            or request.headers.get("X-Guild-Id")
            or settings.main_guild_id
            or ""
        ).strip()
        sess = _extract_session(request, guild_id=target_gid)
        is_adm = bool(sess and sess.get("user", {}).get("isAdmin"))
        if not is_adm:
            raise HTTPException(
                status_code=403,
                detail="Akses Ditolak: Fitur ini dikhususkan untuk Admin Server pada server ini.",
            )

    def _verify_and_sync_requester_voice_channel(
        guild_id: str,
        requester_id: str,
        requester_name: str,
        is_admin: bool,
        has_dj_role: bool,
    ) -> Optional[JSONResponse]:
        """
        Memastikan pemutaran/kontrol musik dari Web Player WAJIB mengikuti Voice Channel
        dari user Discord yang sedang login (requester_id).
        Jika User B login di Web Player tetapi tidak join Voice Channel, bot TIDAK BOLEH
        masuk atau memutar musik ke Voice Channel User A yang sedang aktif di Discord.
        """
        live_bot = getattr(app.state, "bot", None)
        if live_bot is None or not guild_id.isdigit():
            return None
        try:
            is_bot_ready = bool(getattr(live_bot, "is_ready", lambda: False)())
        except Exception:
            is_bot_ready = False
        if not is_bot_ready:
            return None

        guild_obj = live_bot.get_guild(int(guild_id))
        if guild_obj is None:
            return None

        member_obj = guild_obj.get_member(int(requester_id)) if str(requester_id).isdigit() else None
        user_vc = member_obj.voice.channel if (member_obj and getattr(member_obj, "voice", None)) else None

        if user_vc is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": (
                        f"Akun Discord kamu ({requester_name}) belum masuk ke Voice Channel di server "
                        f"'{guild_obj.name}'! Silakan join Voice Channel Discord terlebih dahulu agar bot mengikuti voice channel kamu."
                    )
                },
            )

        bot_vc = guild_obj.voice_client
        if bot_vc and bot_vc.is_connected() and getattr(bot_vc, "channel", None) and bot_vc.channel.id != user_vc.id:
            humans_in_bot_vc = [m for m in getattr(bot_vc.channel, "members", []) if not getattr(m, "bot", False)]
            if humans_in_bot_vc and not (is_admin or has_dj_role):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": f"Bot sedang aktif digunakan di Voice Channel '{bot_vc.channel.name}'. Masuk ke channel tersebut terlebih dahulu!"
                    },
                )

        st = queue_service.get_state(guild_id)
        st.voice_channel_id = str(user_vc.id)
        st.voice_channel_name = str(user_vc.name)
        return None

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    @app.post("/api/guilds/{guild_id}/music/play")
    async def api_music_play(guild_id: str, request: Request):
        validate_snowflake_param("guild_id", guild_id)
        body = await request.json()
<<<<<<< HEAD
        sess = _extract_session(request, guild_id=guild_id)
        requester_id = sess["user"]["id"] if sess else str(body.get("requester_id", "")).strip()
        requester_name = sess["user"]["name"] if sess else str(body.get("requester_name", "Member Server")).strip()
        is_admin = bool(sess["user"]["isAdmin"]) if sess else bool(body.get("is_admin", False))
        has_dj_role = bool(sess["user"]["hasDjRole"]) if sess else bool(body.get("has_dj_role", False) or is_admin)

        if not requester_id:
            return JSONResponse(
                status_code=401,
                content={"error": "Wajib login menggunakan akun Discord terlebih dahulu untuk memutar musik."},
            )

        vc_err = _verify_and_sync_requester_voice_channel(
            guild_id=guild_id,
            requester_id=requester_id,
            requester_name=requester_name,
            is_admin=is_admin,
            has_dj_role=has_dj_role,
        )
        if vc_err is not None:
            return vc_err
=======
        sess = _extract_session(request)
        requester_id = sess["user"]["id"] if sess else str(body.get("requester_id", "guest"))
        requester_name = sess["user"]["name"] if sess else str(body.get("requester_name", "Member Server"))
        is_admin = sess["user"]["isAdmin"] if sess else bool(body.get("is_admin", False) or body.get("is_owner", False))
        has_dj_role = sess["user"]["hasDjRole"] if sess else bool(body.get("has_dj_role", False) or is_admin)

        live_bot = getattr(app.state, "bot", None)
        if live_bot is not None and guild_id.isdigit() and not (is_admin or has_dj_role):
            guild_obj = live_bot.get_guild(int(guild_id))
            if guild_obj is not None:
                member_obj = guild_obj.get_member(int(requester_id)) if requester_id.isdigit() else None
                user_vc = member_obj.voice.channel if (member_obj and member_obj.voice) else None
                bot_vc = guild_obj.voice_client
                if bot_vc and bot_vc.is_connected() and bot_vc.channel and user_vc and bot_vc.channel.id != user_vc.id:
                    humans_in_bot_vc = [m for m in bot_vc.channel.members if not m.bot]
                    if humans_in_bot_vc:
                        return JSONResponse(
                            status_code=400,
                            content={
                                "error": f"Bot sedang digunakan di Voice Channel '{bot_vc.channel.name}'. Masuk ke channel tersebut terlebih dahulu!"
                            },
                        )
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

        raw_source_url = str(body.get("source_url", "")).strip()
        raw_source_type = str(body.get("source_type", "spotify_matched")).strip()
        play_now_flag = bool(body.get("play_now", False))

        try:
            input_kind = ""
            try:
                input_kind, _ = classify_music_input(raw_source_url)
            except Exception:
                input_kind = ""

            if raw_source_type in ("spotify_playlist", "spotify_album", "youtube_playlist") or input_kind in (
                "spotify_playlist",
                "spotify_album",
                "youtube_playlist",
            ):
                pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, raw_source_url, 50)
                pl_tracks = pl_data.get("tracks") or []
                if not pl_tracks:
                    return JSONResponse(status_code=404, content={"error": "Playlist kosong atau tidak terbaca."})

                is_yt_pl = raw_source_type == "youtube_playlist" or input_kind == "youtube_playlist"
                default_album = "YouTube Playlist" if is_yt_pl else "Spotify Playlist"
                default_src_type = "youtube" if is_yt_pl else "spotify_matched"
                first_item = None
                started_any = False
                for idx, tr in enumerate(pl_tracks):
                    item_added, started = queue_service.add_track(
                        guild_id=guild_id,
                        title=tr.title,
                        artist=tr.artist,
                        album=tr.album or str(pl_data.get("playlist_name") or default_album),
                        duration_sec=int(tr.duration_sec or 180),
                        source_type=getattr(tr, "source_type", "") or default_src_type,
                        source_url=tr.source_url,
                        stream_url="",
                        thumbnail_url=tr.thumbnail_url,
                        requester_id=requester_id,
                        requester_name=requester_name,
                        play_now=(play_now_flag and idx == 0),
                        user_roles=body.get("user_roles") or [],
                        is_admin=is_admin,
                        is_owner=is_admin,
                        dj_role_id=settings.dj_role_id,
                        has_dj_role=has_dj_role,
                    )
                    if idx == 0:
                        first_item = item_added
                    if started:
                        started_any = True

                await _broadcast_guild_state(guild_id)
                return {
                    "item": asdict(first_item) if first_item else {},
                    "playlist_tracks_added": len(pl_tracks),
                    "started_immediately": started_any,
                    "state": _serialize_music_state(guild_id),
                }

            item, started = queue_service.add_track(
                guild_id=guild_id,
                title=str(body.get("title", "Unknown")),
                artist=str(body.get("artist", "Unknown")),
                album=str(body.get("album", "")),
                duration_sec=int(body.get("duration_sec", 180)),
                source_type=raw_source_type,
                source_url=raw_source_url,
                stream_url=str(body.get("stream_url", "")),
                thumbnail_url=str(body.get("thumbnail_url", "")),
                requester_id=requester_id,
                requester_name=requester_name,
                play_now=play_now_flag,
                user_roles=body.get("user_roles") or [],
                is_admin=is_admin,
                is_owner=is_admin,
                dj_role_id=settings.dj_role_id,
                has_dj_role=has_dj_role,
            )
            return {
                "item": asdict(item),
                "started_immediately": started,
                "state": _serialize_music_state(guild_id),
            }
        except PermissionError as exc:
            return JSONResponse(status_code=403, content={"error": str(exc)})

    @app.post("/api/guilds/{guild_id}/music/control")
    async def api_music_control(guild_id: str, request: Request):
        validate_snowflake_param("guild_id", guild_id)
        body = await request.json()
<<<<<<< HEAD
        sess = _extract_session(request, guild_id=guild_id)
        actor_id = sess["user"]["id"] if sess else str(body.get("actor_id", "")).strip()
        actor_name = sess["user"]["name"] if sess else str(body.get("actor_name", "Member Server")).strip()
        is_admin = bool(sess["user"]["isAdmin"]) if sess else bool(body.get("is_admin", False))
        has_dj_role = bool(sess["user"]["hasDjRole"]) if sess else bool(body.get("has_dj_role", False) or is_admin)
=======
        sess = _extract_session(request)
        actor_id = sess["user"]["id"] if sess else str(body.get("actor_id", ""))
        is_admin = sess["user"]["isAdmin"] if sess else bool(body.get("is_admin", False) or body.get("is_owner", False))
        has_dj_role = sess["user"]["hasDjRole"] if sess else bool(body.get("has_dj_role", False) or is_admin)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        action = str(body.get("action", ""))
        item_id = str(body.get("item_id", ""))
        val = body.get("value")

<<<<<<< HEAD
        if action in ("play_item", "pause", "resume", "skip", "stop", "seek", "volume", "shuffle", "clear", "loop"):
            vc_err = _verify_and_sync_requester_voice_channel(
                guild_id=guild_id,
                requester_id=actor_id,
                requester_name=actor_name,
                is_admin=is_admin,
                has_dj_role=has_dj_role,
            )
            if vc_err is not None:
                return vc_err

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        try:
            if action == "play_item":
                queue_service.play_queue_item(
                    guild_id=guild_id,
                    item_id=item_id,
                    actor_id=actor_id,
                    user_roles=body.get("user_roles") or [],
                    is_admin=is_admin,
                    is_owner=is_admin,
                    dj_role_id=settings.dj_role_id,
                    has_dj_role=has_dj_role,
                )
                live_bot = getattr(app.state, "bot", None)
                if live_bot is not None and hasattr(live_bot, "apply_web_control"):
                    try:
                        asyncio.create_task(live_bot.apply_web_control(guild_id, "play_item", item_id))
                    except Exception:
                        pass
            elif action == "remove_item":
                queue_service.remove_item(
                    guild_id=guild_id,
                    item_id=item_id,
                    actor_id=actor_id,
                    user_roles=body.get("user_roles") or [],
                    is_admin=is_admin,
                    is_owner=is_admin,
                    dj_role_id=settings.dj_role_id,
                    has_dj_role=has_dj_role,
                )
            elif action == "move_to_top":
                queue_service.move_to_top(
                    guild_id=guild_id,
                    item_id=item_id,
                    actor_id=actor_id,
                    user_roles=body.get("user_roles") or [],
                    is_admin=is_admin,
                    is_owner=is_admin,
                    dj_role_id=settings.dj_role_id,
                    has_dj_role=has_dj_role,
                )
            else:
                st = queue_service.control_session(
                    guild_id=guild_id,
                    action=action,
                    actor_id=actor_id,
                    user_roles=body.get("user_roles") or [],
                    is_admin=is_admin,
                    is_owner=is_admin,
                    dj_role_id=settings.dj_role_id,
                    value=val,
                    has_dj_role=has_dj_role,
                )
                if action in ("autoplay", "mode_247", "volume"):
                    try:
                        with db_manager.transaction() as conn:
                            conn.execute(
                                """
                                UPDATE guild_settings
                                SET autoplay = ?, mode_247 = ?, default_volume = ?, updated_at = ?
                                WHERE guild_id = ?
                                """,
                                (
                                    1 if st.autoplay else 0,
                                    1 if st.mode_247 else 0,
                                    st.volume,
                                    _utc_now(),
                                    guild_id,
                                ),
                            )
                    except Exception:
                        pass
                live_bot = getattr(app.state, "bot", None)
                if live_bot is not None and hasattr(live_bot, "apply_web_control"):
                    try:
                        asyncio.create_task(live_bot.apply_web_control(guild_id, action, val))
                    except Exception:
                        pass

            await _broadcast_guild_state(guild_id)
            return {"ok": True, "state": _serialize_music_state(guild_id)}
        except (PermissionError, KeyError, ValueError) as exc:
            return JSONResponse(status_code=403, content={"error": str(exc)})

    # =========================================================================
    # Direct Playlist Playback Endpoint (Spotify Playlist/Album & YouTube Playlist)
    # Tanpa penyimpanan koleksi playlist atau favorit
    # =========================================================================
    @app.post("/api/guilds/{guild_id}/music/play-playlist")
    @app.post("/api/guilds/{guild_id}/playlists/import-spotify")
    async def api_play_playlist_direct(guild_id: str, request: Request):
        body = await request.json()
<<<<<<< HEAD
        sess = _extract_session(request, guild_id=guild_id)
        owner_id = sess["user"]["id"] if sess else str(body.get("owner_user_id") or "").strip()
        owner_name = sess["user"]["name"] if sess else str(body.get("owner_username") or "Member Server").strip()
        is_adm = bool(sess["user"]["isAdmin"]) if sess else bool(body.get("is_admin", False))
        has_dj = bool(sess["user"]["hasDjRole"]) if sess else bool(body.get("has_dj_role", False) or is_adm)
=======
        sess = _extract_session(request)
        owner_id = sess["user"]["id"] if sess else str(body.get("owner_user_id") or "844174494099701780")
        owner_name = sess["user"]["name"] if sess else str(body.get("owner_username") or "Member Server")
        is_adm = sess["user"]["isAdmin"] if sess else True
        has_dj = sess["user"]["hasDjRole"] if sess else True
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        playlist_url = str(body.get("spotify_url") or body.get("url") or body.get("input") or "").strip()
        custom_name = str(body.get("name") or "").strip()
        queue_now = bool(body.get("queue_now", body.get("play_immediately", True)))

        if not playlist_url:
            return JSONResponse(
                status_code=400,
                content={"error": "Masukkan link Playlist YouTube atau Spotify terlebih dahulu."},
            )

<<<<<<< HEAD
        if queue_now:
            vc_err = _verify_and_sync_requester_voice_channel(
                guild_id=guild_id,
                requester_id=owner_id,
                requester_name=owner_name,
                is_admin=is_adm,
                has_dj_role=has_dj,
            )
            if vc_err is not None:
                return vc_err

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        try:
            pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, playlist_url, 50)
        except Exception as exc:
            return JSONResponse(status_code=400, content={"error": f"Gagal membaca playlist: {exc}"})

        tracks = pl_data.get("tracks") or []
        if not tracks:
            return JSONResponse(status_code=404, content={"error": "Tidak ditemukan lagu di dalam playlist tersebut."})

        playlist_name = custom_name or str(pl_data.get("playlist_name") or "Playlist")

        if queue_now:
            st = queue_service.get_state(guild_id)
            was_empty = st.current_track is None
            for idx, tr in enumerate(tracks):
                queue_service.add_track(
                    guild_id=guild_id,
                    title=tr.title,
                    artist=tr.artist,
                    album=getattr(tr, "album", "") or playlist_name,
                    duration_sec=int(getattr(tr, "duration_sec", 200) or 200),
                    source_type=getattr(tr, "source_type", "") or "spotify_matched",
                    source_url=getattr(tr, "source_url", "") or playlist_url,
                    stream_url=getattr(tr, "stream_url", "") or "",
                    thumbnail_url=getattr(tr, "thumbnail_url", "") or "",
<<<<<<< HEAD
                    requester_id=owner_id or "guest",
=======
                    requester_id=owner_id,
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                    requester_name=owner_name,
                    play_now=(was_empty and idx == 0),
                    is_admin=is_adm,
                    is_owner=is_adm,
                    has_dj_role=has_dj,
                )
            await _broadcast_guild_state(guild_id)

        return {
            "ok": True,
            "name": playlist_name,
            "playlist_name": playlist_name,
            "tracks_count": len(tracks),
            "played": queue_now,
            "state": _serialize_music_state(guild_id),
        }

    # =========================================================================
    # Academy Tasks, Modules & RPG Endpoints
    # =========================================================================
    @app.get("/api/guilds/{guild_id}/tasks")
    async def api_get_tasks(guild_id: str):
        validate_snowflake_param("guild_id", guild_id)
        tasks = [asdict(t) for t in academy_service.list_tasks(guild_id, include_completed=True)]
        with db_manager.transaction() as conn:
            atts = conn.execute("SELECT * FROM task_attachments WHERE guild_id = ?", (guild_id,)).fetchall()
            rems = conn.execute("SELECT * FROM reminder_deliveries WHERE guild_id = ?", (guild_id,)).fetchall()
        return {
            "tasks": tasks,
            "attachments": [dict(a) for a in atts],
            "reminders": [dict(r) for r in rems],
            "moodle_env": academy_service.get_moodle_env_status(),
        }

    @app.post("/api/guilds/{guild_id}/tasks")
    async def api_create_task(guild_id: str, request: Request):
        body = await request.json()
<<<<<<< HEAD
        sess = _extract_session(request, guild_id=guild_id)
        creator = sess["user"]["name"] if sess else str(body.get("created_by", "Aetheriaaa"))
        try:
            safe_course = sanitize_discord_outbound_text(str(body.get("course_name", "Umum")), max_length=120)
            safe_title = sanitize_discord_outbound_text(str(body.get("title", "")), max_length=200)
            safe_desc = sanitize_discord_outbound_text(str(body.get("description", "")), max_length=800)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        task = academy_service.create_task(
            guild_id=guild_id,
            course_name=safe_course or "Umum",
            title=safe_title,
            deadline_iso=str(body.get("deadline_iso", _utc_now())),
            created_by=creator,
            description=safe_desc,
=======
        sess = _extract_session(request)
        creator = sess["user"]["name"] if sess else str(body.get("created_by", "Aetheriaaa"))
        task = academy_service.create_task(
            guild_id=guild_id,
            course_name=str(body.get("course_name", "Umum")),
            title=str(body.get("title", "")),
            deadline_iso=str(body.get("deadline_iso", _utc_now())),
            created_by=creator,
            description=str(body.get("description", "")),
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            source_url=str(body.get("source_url", "")),
        )
        return {"task": asdict(task)}

    @app.patch("/api/guilds/{guild_id}/tasks/{task_id}")
    async def api_patch_task(guild_id: str, task_id: str, request: Request):
        body = await request.json()
<<<<<<< HEAD
        sess = _extract_session(request, guild_id=guild_id)
=======
        sess = _extract_session(request)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        actor_name = sess["user"]["name"] if sess else str(body.get("actor_name", "Aetheriaaa"))
        if "is_completed" in body:
            academy_service.set_task_completion(
                guild_id=guild_id,
                task_id=task_id,
                completed=bool(body["is_completed"]),
                actor_name=actor_name,
            )
        return {"ok": True}

    @app.post("/api/tasks/{task_id}/toggle")
    async def api_toggle_task(task_id: str, request: Request):
        sess = _extract_session(request)
        actor_name = sess["user"]["name"] if sess else "Aetheriaaa"
        updated = academy_service.toggle_task(task_id=task_id, actor_name=actor_name)
        if not updated:
            raise HTTPException(status_code=404, detail="Tugas tidak ditemukan.")
        return {"ok": True, "task": asdict(updated)}

    @app.delete("/api/guilds/{guild_id}/tasks/{task_id}")
    async def api_delete_guild_task(guild_id: str, task_id: str):
        academy_service.delete_task(guild_id, task_id)
        return {"ok": True}

    @app.delete("/api/tasks/{task_id}")
    async def api_delete_task_by_id(task_id: str):
        academy_service.delete_task("", task_id)
        return {"ok": True}

    @app.post("/api/guilds/{guild_id}/tasks/sync-ics")
    @app.post("/api/guilds/{guild_id}/tasks/sync-moodle")
    async def api_sync_moodle(guild_id: str, request: Request):
        validate_snowflake_param("guild_id", guild_id)
        try:
            body = await request.json()
        except Exception:
            body = {}
        ics_content = str(body.get("ics_content", "")).strip()
        ical_url = str(body.get("ical_url", "")).strip()
        moodle_base_url = str(body.get("moodle_base_url", "")).strip()
        moodle_username = str(body.get("moodle_username", "")).strip()
        moodle_password = str(body.get("moodle_password", "")).strip()
        try:
            res = academy_service.sync_moodle_ics_content(
                guild_id=guild_id,
                ics_content=ics_content,
                actor_id="Moodle Sync",
                ical_url=ical_url,
                moodle_base_url=moodle_base_url,
                moodle_username=moodle_username,
                moodle_password=moodle_password,
            )
            return res
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.post("/api/guilds/{guild_id}/modules/upload")
    async def api_upload_module(guild_id: str, request: Request):
        body = await request.json()
<<<<<<< HEAD
        sess = _extract_session(request, guild_id=guild_id)
=======
        sess = _extract_session(request)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        uploader = sess["user"]["name"] if sess else "Aetheriaaa"
        raw_filename = str(body.get("filename", "")).strip()
        size_bytes = int(body.get("size_bytes", 0))
        task_id = str(body.get("task_id", "")).strip()

        if size_bytes <= 0 or size_bytes > 15 * 1024 * 1024:
            return JSONResponse(
                status_code=400,
                content={"error": "Ukuran file tidak valid atau melebihi batas maksimum 15 MB."},
            )

        ext = Path(raw_filename).suffix.lower()
        sample_magic = (
            _build_valid_pdf_bytes(raw_filename, uploader, "new")
            if ext == ".pdf"
            else b"PK\x03\x04 Athenaa DOCX"
            if ext == ".docx"
            else b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 Athenaa DOC"
            if ext == ".doc"
            else b"UNKNOWN"
        )
        ok, err_msg, stored_name = sanitize_and_validate_attachment(raw_filename, sample_magic, max_mb=15)
        if not ok:
            return JSONResponse(status_code=400, content={"error": err_msg})

        mime_type = (
            "application/pdf"
            if ext == ".pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if ext == ".docx"
            else "application/msword"
        )

        content_b64 = str(body.get("content_base64", "")).strip()
        if content_b64:
            if "," in content_b64:
                content_b64 = content_b64.split(",", 1)[1]
            try:
                file_bytes = base64.b64decode(content_b64)
            except Exception:
                file_bytes = sample_magic
        else:
            file_bytes = sample_magic

        target_dirs = [Path("modules")]
        if getattr(settings, "modules_dir", None):
            target_dirs.insert(0, Path(settings.modules_dir))

        for m_dir in target_dirs:
            try:
                m_dir.mkdir(parents=True, exist_ok=True)
                (m_dir / stored_name).write_bytes(file_bytes)
            except Exception:
                pass

        final_size = len(file_bytes) if file_bytes else size_bytes

        att_id = f"att-{uuid.uuid4().hex[:10]}"
        now_iso = _utc_now()
        with db_manager.transaction() as conn:
            if not task_id:
                first_task = conn.execute(
                    "SELECT task_id FROM tasks WHERE guild_id = ? LIMIT 1", (guild_id,)
                ).fetchone()
                if first_task:
                    task_id = str(first_task["task_id"])
                else:
                    created = academy_service.create_task(
                        guild_id=guild_id,
                        course_name="Modul Akademik",
                        title="Referensi Materi Kuliah",
                        deadline_iso=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                        created_by=uploader,
                    )
                    task_id = created.task_id

            conn.execute(
                """
                INSERT INTO task_attachments (
                    attachment_id, task_id, guild_id, original_filename,
                    stored_filename, mime_type, size_bytes, uploaded_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (att_id, task_id, guild_id, raw_filename, stored_name, mime_type, final_size, uploader, now_iso),
            )
        return {
            "ok": True,
            "attachment": {
                "attachment_id": att_id,
                "task_id": task_id,
                "guild_id": guild_id,
                "original_filename": raw_filename,
                "stored_filename": stored_name,
                "mime_type": mime_type,
                "size_bytes": final_size,
                "uploaded_by": uploader,
                "created_at": now_iso,
            },
        }

    @app.get("/api/modules/{attachment_id}/download")
    async def api_download_module(attachment_id: str):
        with db_manager.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM task_attachments WHERE attachment_id = ?",
                (attachment_id,),
            ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Modul tidak ditemukan.")

        row_data = dict(row)
        stored_name = str(row_data.get("stored_filename") or f"{attachment_id}.pdf")

        import re
        safe_filename_pattern = re.compile(r'^[a-f0-9]{32}\.(pdf|doc|docx)$', re.IGNORECASE)
        if not safe_filename_pattern.match(stored_name):
            raise HTTPException(status_code=400, detail="Nama file tidak valid.")

        orig_name = str(row_data.get("original_filename") or stored_name or "modul.pdf")
        mime_type = str(row_data.get("mime_type") or "application/pdf")
        uploader = str(row_data.get("uploaded_by") or "Aetheriaaa")

        candidate_paths = []
        if getattr(settings, "modules_dir", None):
            candidate_paths.append(Path(settings.modules_dir) / stored_name)
        candidate_paths.extend(
            [
                Path("modules") / stored_name,
                Path("data/modules") / stored_name,
                BASE_DIR / "modules" / stored_name,
                BASE_DIR / "data" / "modules" / stored_name,
            ]
        )

        for fp in candidate_paths:
            try:
                fp_resolved = fp.resolve()
                base_resolved = BASE_DIR.resolve()
                modules_resolved = Path(settings.modules_dir).resolve() if getattr(settings, "modules_dir", None) else None
                if not (str(fp_resolved).startswith(str(base_resolved)) or
                        (modules_resolved and str(fp_resolved).startswith(str(modules_resolved)))):
                    continue
            except Exception:
                continue

            if fp.is_file() and fp.stat().st_size > 0:
                return FileResponse(
                    path=str(fp),
                    filename=orig_name,
                    media_type=mime_type,
                )

        fallback_dir = Path(getattr(settings, "modules_dir", None) or Path("modules"))
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback_file = fallback_dir / stored_name
        pdf_bytes = _build_valid_pdf_bytes(orig_name, uploader, attachment_id)
        fallback_file.write_bytes(pdf_bytes)

        return FileResponse(
            path=str(fallback_file),
            filename=orig_name,
            media_type=mime_type,
        )

    @app.delete("/api/guilds/{guild_id}/modules/{attachment_id}")
<<<<<<< HEAD
    async def api_delete_guild_module(guild_id: str, attachment_id: str, request: Request):
        validate_snowflake_param("guild_id", guild_id)
        _require_admin(request)
=======
    async def api_delete_guild_module(guild_id: str, attachment_id: str):
        validate_snowflake_param("guild_id", guild_id)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        deleted = academy_service.delete_attachment(guild_id, attachment_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Modul atau lampiran tidak ditemukan.")
        return {"ok": True, "deleted_id": attachment_id, "attachment": deleted}

    @app.delete("/api/modules/{attachment_id}")
<<<<<<< HEAD
    async def api_delete_module_direct(attachment_id: str, request: Request):
        _require_admin(request)
=======
    async def api_delete_module_direct(attachment_id: str):
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        deleted = academy_service.delete_attachment("", attachment_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Modul atau lampiran tidak ditemukan.")
        return {"ok": True, "deleted_id": attachment_id, "attachment": deleted}

    @app.get("/api/guilds/{guild_id}/rpg")
    async def api_guild_rpg(guild_id: str):
        validate_snowflake_param("guild_id", guild_id)
        return {
            "leaderboard": leveling_service.get_leaderboard(guild_id, limit=15),
            "afk_list": leveling_service.list_afk(guild_id),
        }

    @app.post("/api/guilds/{guild_id}/rpg/activity")
    async def api_rpg_activity(guild_id: str, request: Request):
<<<<<<< HEAD
        sess = _extract_session(request, guild_id=guild_id)
        body = await request.json()
        is_adm = bool(sess and sess.get("user", {}).get("isAdmin"))
=======
        sess = _extract_session(request)
        body = await request.json()
        is_adm = bool(sess and sess.get("user", {}).get("isAdmin")) or bool(body.get("is_admin", False))
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        if not is_adm:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Akses Ditolak: Fitur Uji Aktivitas & Simulasi EXP hanya dapat diakses oleh Admin Server."
                },
            )

        uid = sess["user"]["id"] if sess else str(body.get("user_id") or "844174494099701780")
        uname = (sess["user"]["discordTag"].lstrip("@") if sess else "admin_server") or "admin_server"
        dname = sess["user"]["name"] if sess else "Admin Server"
        activity_type = str(body.get("activity_type", "chat")).strip().lower()
        msg = str(body.get("message_content", "Aktivitas di server Discord"))
        bypass = bool(body.get("bypass_cooldown", False))

        if activity_type in ("voice_join", "voice_speak", "voice_listen", "voice_stream", "minigame"):
            leveled_up, level, current_exp, max_exp = leveling_service.process_voice_activity(
                guild_id=guild_id,
                user_id=uid,
                username=uname,
                display_name=dname,
                activity_type=activity_type,
                is_bot=False,
                cooldown_seconds=0 if bypass else 45,
            )
        else:
            leveled_up, level, current_exp, max_exp = leveling_service.process_message_activity(
                guild_id=guild_id,
                user_id=uid,
                username=uname,
                display_name=dname,
                message_content=msg,
                is_bot=False,
                cooldown_seconds=0 if bypass else 60,
                exp_gain=25,
            )
        return {
            "ok": True,
            "activity_type": activity_type,
            "leveled_up": leveled_up,
            "level": level,
            "current_exp": current_exp,
            "max_exp": max_exp,
        }

    @app.post("/api/guilds/{guild_id}/afk")
    async def api_set_afk(guild_id: str, request: Request):
        validate_snowflake_param("guild_id", guild_id)
        body = await request.json()
<<<<<<< HEAD
        sess = _extract_session(request, guild_id=guild_id)
        uid = sess["user"]["id"] if sess else str(body.get("user_id") or "844174494099701780")
        uname = sess["user"]["name"] if sess else str(body.get("username") or "Member Server")
        try:
            safe_reason = sanitize_discord_outbound_text(str(body.get("reason", "Sedang AFK")), max_length=160)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
=======
        sess = _extract_session(request)
        uid = sess["user"]["id"] if sess else str(body.get("user_id") or "844174494099701780")
        uname = sess["user"]["name"] if sess else str(body.get("username") or "Member Server")
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        leveling_service.set_afk(
            guild_id=guild_id,
            user_id=uid,
            username=uname,
<<<<<<< HEAD
            reason=safe_reason or "Sedang AFK",
=======
            reason=str(body.get("reason", "Sedang AFK")),
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        )
        return {"ok": True}

    @app.delete("/api/guilds/{guild_id}/afk/{user_id}")
    async def api_clear_afk(guild_id: str, user_id: str):
        validate_snowflake_param("guild_id", guild_id)
        leveling_service.clear_afk(guild_id, user_id)
        return {"ok": True}

<<<<<<< HEAD
=======
    # =========================================================================
    # Admin Server Endpoints (Per-Server Scoped; Codebase & ZIP Download Hidden)
    # =========================================================================
    def _require_admin(request: Request) -> None:
        target_gid = (
            request.path_params.get("guild_id")
            or request.query_params.get("guild_id")
            or request.headers.get("X-Guild-Id")
            or settings.main_guild_id
            or ""
        ).strip()
        sess = _extract_session(request, guild_id=target_gid)
        is_adm = bool(sess and sess.get("user", {}).get("isAdmin"))
        if not is_adm and request.query_params.get("role", "").lower() == "admin":
            # Hanya izinkan query param fallback jika user tidak sedang dibatasi pada server non-admin
            if not (sess and sess.get("user", {}).get("guildRoles") and target_gid):
                is_adm = True
        if not is_adm:
            raise HTTPException(
                status_code=403,
                detail="Akses Ditolak: Fitur ini dikhususkan untuk Admin Server pada server ini.",
            )

>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    @app.get("/api/admin/metrics")
    async def api_admin_metrics(request: Request):
        _require_admin(request)
        return get_system_metrics(is_admin=True)

    @app.post("/api/admin/backup")
    async def api_admin_backup(request: Request):
        _require_admin(request)
        return backup_service.create_consistent_backup(encrypt=True)

    @app.post("/api/admin/yt-dlp")
    async def api_admin_ytdlp(request: Request):
        _require_admin(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        return BackupService.check_and_update_ytdlp(perform_update=bool(body.get("perform_update", False)))

    @app.post("/api/admin/run-tests")
    async def api_admin_tests(request: Request):
        _require_admin(request)
        return run_test_suite()

    @app.get("/api/python-codebase")
    async def api_python_codebase(request: Request):
        return JSONResponse(
            status_code=403,
            content={"error": "Kode sumber bot disembunyikan dan dinonaktifkan untuk semua role."},
        )

    @app.get("/api/python-codebase/download-zip")
    async def api_download_zip(request: Request):
        return JSONResponse(
            status_code=403,
            content={"error": "Unduhan file .zip kode bot dinonaktifkan."},
        )

    # =========================================================================
    # Serve Pre-Built Spotify React Web UI (app/web/static) on Port 10031
    # =========================================================================
    if (STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        active_static_dir = _resolve_static_dir()
        candidate = (active_static_dir / full_path).resolve()
        if (
            full_path
            and str(candidate).startswith(str(active_static_dir.resolve()))
            and candidate.is_file()
        ):
            return FileResponse(str(candidate))
        index_html = active_static_dir / "index.html"
        if index_html.exists():
            raw_html = index_html.read_text(encoding="utf-8", errors="ignore")
            return HTMLResponse(raw_html)
        return JSONResponse({"status": "Athenaa API Running", "web_ui": "Static UI siap dimuat"})

    _ACTIVE_BROADCAST_CBS.append(_broadcast_guild_state)
    return app


_ACTIVE_BROADCAST_CBS: List[Any] = []


async def notify_guild_state_updated(guild_id: str) -> None:
    """Callback async untuk memberitahu seluruh WebSocket client saat state guild berubah."""
    for cb in list(_ACTIVE_BROADCAST_CBS):
        try:
            await cb(guild_id)
        except Exception:
            pass


build_fastapi_app = create_fastapi_app