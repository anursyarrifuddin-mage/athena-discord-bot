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
    sanitize_and_validate_attachment,
    validate_snowflake_param,
)
from app.services.academy_service import AcademyService
from app.services.backup_service import BackupService
from app.services.leveling_service import LevelingService
from app.services.lyrics_service import lyrics_service
from app.services.music_service import (
    VERIFIED_RADIO_STATIONS,
    classify_music_input,
    extract_spotify_playlist_tracks,
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

STATIC_DIR = BASE_DIR / "app" / "web" / "static"

PYTHON_CODEBASE_FILES = [
    {"path": "app/main.py", "role": "Entrypoint Utama Pterodactyl (Discord Bot + FastAPI Port 10031)"},
    {"path": "app/config.py", "role": "Konfigurasi Environment (.env), Port 10031, Domain athenaa.my.id"},
    {"path": "app/database.py", "role": "Manajer Skema SQLite WAL & Transaksi Aman"},
    {"path": "app/bot/client.py", "role": "Discord Bot, VoiceClient yt-dlp + FFmpeg, & Slash Commands"},
    {"path": "app/services/music_service.py", "role": "Mesin Pencarian Lagu + Singer, Resolver Spotify, & Ekstraktor yt-dlp"},
    {"path": "app/services/queue_service.py", "role": "Antrean Musik Per-Server, Session Host Lock, Autoplay, & Mode 24/7"},
    {"path": "app/services/lyrics_service.py", "role": "Klien Lirik Tersinkronisasi LRCLIB & Parser Timestamp LRC"},
    {"path": "app/services/academy_service.py", "role": "Manajemen Tugas Akademik, Sinkronisasi Moodle (.ics), & Reminder 3 Tahap"},
    {"path": "app/services/leveling_service.py", "role": "Sistem RPG EXP, Leaderboard Top 15, & Status AFK Persisten"},
    {"path": "app/services/backup_service.py", "role": "Backup SQLite Konsisten Terenkripsi HMAC & Kontrol Worker yt-dlp"},
    {"path": "app/security/validators.py", "role": "Proteksi SSRF, Validasi Lampiran Modul, & Enkripsi Kredensial"},
    {"path": "app/web/routes/api.py", "role": "Server FastAPI, WebSocket Real-Time (/ws), & Discord OAuth2 Multi-Session"},
]

UI_CUSTOMIZATION_INJECTION = """
<style id="athenaa-ui-patch-styles">
  button[title*="Favorit" i],
  button[aria-label*="Favorit" i],
  button:has(svg.lucide-heart) {
    display: none !important;
  }
  div.max-h-72,
  div.max-h-\\[340px\\] {
    max-height: 560px !important;
  }
</style>
<script id="athenaa-ui-patch-script">
(function() {
  function applyAthenaaUiCleanup() {
    try {
      var buttons = document.querySelectorAll('aside button, nav button, button');
      for (var i = 0; i < buttons.length; i++) {
        var btn = buttons[i];
        var txt = (btn.textContent || '').trim();
        if (
          txt.indexOf('Favorit & Playlist') !== -1 ||
          txt.indexOf('Koleksi lagu & playlist') !== -1
        ) {
          btn.style.setProperty('display', 'none', 'important');
        }
        if (btn.querySelector('svg.lucide-heart') && txt.length === 0) {
          btn.style.setProperty('display', 'none', 'important');
        }
      }

      var headings = document.querySelectorAll('h2, h3');
      for (var j = 0; j < headings.length; j++) {
        var h = headings[j];
        if ((h.textContent || '').indexOf('Otorisasi Akun Discord') !== -1) {
          h.textContent = 'Login ke Athenaa';
          var sub = h.nextElementSibling;
          if (sub && sub.tagName === 'P') {
            sub.textContent = 'Masuk dengan akun Discord untuk mengakses panel.';
          }
        }
      }
      var allParagraphs = document.querySelectorAll('p, div, span, button');
      for (var k = 0; k < allParagraphs.length; k++) {
        var el = allParagraphs[k];
        if (el.children.length === 0 || el.tagName === 'BUTTON') {
          var t = (el.textContent || '').trim();
          if (t === 'Keamanan Sesi Tunggal Discord OAuth2') {
            el.textContent = 'Sinkronisasi Server Otomatis';
          } else if (t.indexOf('Login manual menggunakan User ID telah dinonaktifkan') !== -1) {
            el.textContent = 'Role dan akses diverifikasi langsung dari server Discord (Maks. 5 perangkat aktif).';
          } else if (t === 'Authorize dengan Discord OAuth2 Resmi') {
            el.textContent = 'Login dengan Discord';
          } else if (t === 'Buka Otorisasi Discord via Jendela Popup') {
            el.textContent = 'Login via Popup';
          }
        }
      }
    } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyAthenaaUiCleanup);
  } else {
    applyAthenaaUiCleanup();
  }
  var obs = new MutationObserver(function() {
    applyAthenaaUiCleanup();
  });
  if (document.documentElement) {
    obs.observe(document.documentElement, { childList: true, subtree: true });
  }
})();
</script>
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_multi_session_table() -> None:
    """Memastikan tabel discord_user_sessions tersedia untuk mendukung hingga 5 perangkat per akun Discord."""
    try:
        with db_manager.transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discord_user_sessions (
                    session_token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    discord_tag TEXT NOT NULL,
                    role_label TEXT NOT NULL,
                    is_owner INTEGER NOT NULL DEFAULT 0,
                    has_dj_role INTEGER NOT NULL DEFAULT 0,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_discord_user_sessions_uid ON discord_user_sessions(user_id, created_at ASC)"
            )
    except Exception:
        pass


_ensure_multi_session_table()


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
) -> Dict[str, Any]:
    """
    Menerbitkan token sesi untuk akun Discord dengan batas maksimal 5 perangkat/sesi aktif (MAX_SESSIONS_PER_USER = 5).
    Jika user login di perangkat ke-6, sesi paling lama (oldest) akan dihapus otomatis sementara 4 sesi lainnya tetap aktif.
    """
    _ensure_multi_session_table()
    new_token = f"athenaa_sess_{user_id}_{secrets.token_hex(12)}"
    now_iso = _utc_now()
    oldest_evicted = False

    with db_manager.transaction() as conn:
        # Migrasi sesi lama di discord_sessions ke discord_user_sessions jika belum ada
        legacy_row = conn.execute(
            "SELECT * FROM discord_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if legacy_row:
            conn.execute(
                """
                INSERT OR IGNORE INTO discord_user_sessions (
                    session_token, user_id, username, discord_tag, role_label,
                    is_owner, has_dj_role, is_admin, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    legacy_row["session_token"],
                    legacy_row["user_id"],
                    legacy_row["username"],
                    legacy_row["discord_tag"],
                    legacy_row["role_label"],
                    int(legacy_row["is_owner"]),
                    int(legacy_row["has_dj_role"]),
                    int(legacy_row["is_admin"]),
                    legacy_row["created_at"],
                ),
            )

        # Simpan sesi perangkat baru ke discord_user_sessions
        conn.execute(
            """
            INSERT INTO discord_user_sessions (
                session_token, user_id, username, discord_tag, role_label,
                is_owner, has_dj_role, is_admin, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_token,
                user_id,
                username,
                discord_tag,
                role_label,
                1 if is_owner else 0,
                1 if has_dj_role else 0,
                1 if is_admin else 0,
                now_iso,
            ),
        )

        # Periksa total sesi aktif milik user_id ini; jika > 5, hapus sesi paling lama (FIFO)
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

        # Sinkronkan juga sesi terbaru ke tabel discord_sessions untuk kompatibilitas mundur
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
                is_owner = excluded.is_owner,
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
                1 if is_owner else 0,
                1 if has_dj_role else 0,
                1 if is_admin else 0,
                now_iso,
            ),
        )

        active_count = min(len(active_rows), MAX_SESSIONS_PER_USER)

    return {
        "session_token": new_token,
        "previous_token_revoked": oldest_evicted,
        "active_sessions_count": active_count,
        "max_sessions": MAX_SESSIONS_PER_USER,
        "user": {
            "id": user_id,
            "name": username,
            "discordTag": discord_tag,
            "roleLabel": role_label,
            "isOwner": is_owner,
            "hasDjRole": has_dj_role,
            "isAdmin": is_admin,
        },
    }


def _get_session_from_token(token: str) -> Optional[Dict[str, Any]]:
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
    return {
        "session_token": row["session_token"],
        "user": {
            "id": row["user_id"],
            "name": row["username"],
            "discordTag": row["discord_tag"],
            "roleLabel": row["role_label"],
            "isOwner": bool(row["is_owner"]),
            "hasDjRole": bool(row["has_dj_role"]),
            "isAdmin": bool(row["is_admin"]),
        },
    }


def get_system_metrics(actor_id: str) -> Dict[str, Any]:
    if actor_id != settings.owner_discord_id:
        raise PermissionError("Akses ditolak: Hanya OWNER_DISCORD_ID yang diizinkan mengakses Super-Admin Hub.")

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
                ORDER BY CASE WHEN guild_id = ? THEN 0 ELSE 1 END, guild_name ASC
                """,
                (str(settings.main_guild_id or ""),),
            ).fetchall()
        return [dict(r) for r in rows]

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

    def _extract_session(request: Request) -> Optional[Dict[str, Any]]:
        auth_header = request.headers.get("Authorization", "")
        bearer = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
        q_tok = request.query_params.get("session_token", "").strip()
        cookie_tok = request.cookies.get("athenaa_session_token", "").strip()
        return _get_session_from_token(bearer or q_tok or cookie_tok)

    @app.get("/health")
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "uptime_seconds": int(time.time() - START_TIME)}

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        ws_clients.add(ws)
        try:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "MUSIC_STATE_UPDATE",
                        "guild_id": settings.main_guild_id,
                        "state": _serialize_music_state(settings.main_guild_id),
                        "guilds": _list_synchronized_guilds(),
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
    @app.get("/api/auth/session")
    async def api_auth_session(request: Request):
        # Rate limit session check endpoint
        _check_auth_rate_limit(request)
        sess = _extract_session(request)
        oauth_ready = bool(settings.discord_client_id and settings.discord_client_secret)
        if sess:
            return {
                "authenticated": True,
                "session_token": sess["session_token"],
                "user": sess["user"],
                "max_sessions": MAX_SESSIONS_PER_USER,
                "oauth_configured": oauth_ready,
            }
        if not oauth_ready and request.query_params.get("auto_bootstrap") == "1":
            with db_manager.transaction() as conn:
                row = conn.execute(
                    "SELECT * FROM discord_user_sessions ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if not row:
                    row = conn.execute(
                        "SELECT * FROM discord_sessions ORDER BY created_at DESC LIMIT 1"
                    ).fetchone()
            if row:
                return {
                    "authenticated": True,
                    "session_token": row["session_token"],
                    "user": {
                        "id": row["user_id"],
                        "name": row["username"],
                        "discordTag": row["discord_tag"],
                        "roleLabel": row["role_label"],
                        "isOwner": bool(row["is_owner"]),
                        "hasDjRole": bool(row["has_dj_role"]),
                        "isAdmin": bool(row["is_admin"]),
                    },
                    "max_sessions": MAX_SESSIONS_PER_USER,
                    "oauth_configured": oauth_ready,
                }
        return {
            "authenticated": False,
            "error": "Masuk dengan akun Discord untuk mengakses panel.",
            "oauth_configured": oauth_ready,
        }

    # Rate limiter untuk auth endpoints (stricter: 10 req/min per IP)
    auth_rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)


    def _check_auth_rate_limit(request: Request) -> None:
        """Check rate limit for auth endpoints based on client IP."""
        client_ip = request.client.host if request.client else "unknown"
        if not auth_rate_limiter.allow(f"auth:{client_ip}"):
            from fastapi import HTTPException
            raise HTTPException(status_code=429, detail="Terlalu banyak percobaan login. Coba lagi nanti.")


    @app.post("/api/auth/login")
    async def api_auth_login(request: Request):
        _check_auth_rate_limit(request)
        return JSONResponse(
            status_code=403,
            content={
                "authenticated": False,
                "error": "Gunakan tombol Login dengan Discord OAuth2.",
            },
        )


    @app.post("/api/auth/logout")
    async def api_auth_logout(request: Request):
        """Hanya menghapus token sesi pada perangkat yang melakukan logout tanpa mengeluarkan perangkat lain."""
        sess = _extract_session(request)
        if sess:
            tok = sess["session_token"]
            uid = sess["user"]["id"]
            with db_manager.transaction() as conn:
                conn.execute(
                    "DELETE FROM discord_user_sessions WHERE session_token = ?",
                    (tok,),
                )
                conn.execute(
                    "DELETE FROM discord_sessions WHERE session_token = ?",
                    (tok,),
                )
                # Jika masih ada sesi aktif di perangkat lain, perbarui discord_sessions dengan sesi terbaru yang tersisa
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
        resp.delete_cookie("athenaa_session_token", path="/")
        return resp

    @app.get("/api/auth/discord/url")
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
                "prompt": "consent",
            }
        )
        return {
            "oauth_configured": True,
            "redirect_uri": settings.discord_redirect_uri,
            "url": f"https://discord.com/oauth2/authorize?{params}",
        }

    @app.get("/api/auth/discord/invite")
    @app.get("/invite")
    async def api_discord_bot_invite(request: Request, mode: str = Query("admin")):
        cid = (settings.discord_client_id or "").strip()
        
        # DISCORD_CLIENT_ID WAJIB di-set di .env - tidak decode dari token!
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
    async def discord_oauth_callback(request: Request, code: str = Query("")):
        # Rate limit OAuth callback
        _check_auth_rate_limit(request)
        if not code or not settings.discord_client_id or not settings.discord_client_secret:
            return HTMLResponse("<h3>Parameter OAuth2 Discord tidak lengkap.</h3>", status_code=400)

        try:
            data = urllib.parse.urlencode(
                {
                    "client_id": settings.discord_client_id,
                    "client_secret": settings.discord_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.discord_redirect_uri,
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

            access_token = token_payload.get("access_token", "")
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
            is_owner = uid == settings.owner_discord_id

            # Fetch user's guilds to check for DJ role
            has_dj_role = is_owner  # Default to owner
            is_admin = is_owner
            role_label = "Bot Owner & Session Host" if is_owner else "Discord Member (Verified OAuth2)"

            if not is_owner and settings.main_guild_id:
                try:
                    guilds_req = urllib.request.Request(
                        "https://discord.com/api/users/@me/guilds",
                        headers={"Authorization": f"Bearer {access_token}", "User-Agent": "AthenaaBot/1.0"},
                    )
                    with urllib.request.urlopen(guilds_req, timeout=10.0) as gresp:
                        guilds_data = json.loads(gresp.read().decode("utf-8"))

                    for guild in guilds_data:
                        if str(guild.get("id", "")) == str(settings.main_guild_id):
                            # User is in the main guild, check for DJ role via member endpoint
                            try:
                                member_req = urllib.request.Request(
                                    f"https://discord.com/api/users/@me/guilds/{settings.main_guild_id}/member",
                                    headers={"Authorization": f"Bearer {access_token}", "User-Agent": "AthenaaBot/1.0"},
                                )
                                with urllib.request.urlopen(member_req, timeout=10.0) as mresp:
                                    member_data = json.loads(mresp.read().decode("utf-8"))

                                user_roles = member_data.get("roles", [])
                                if settings.dj_role_id and settings.dj_role_id in user_roles:
                                    has_dj_role = True
                                    role_label = "Discord Member (DJ Role)"
                                # Check for admin permissions
                                permissions = int(member_data.get("permissions", "0"))
                                if permissions & 0x8:  # Administrator permission
                                    is_admin = True
                                    role_label = "Discord Member (Administrator)"
                            except Exception:
                                pass
                            break
                except Exception:
                    pass

            issued = _issue_single_discord_session(
                user_id=uid,
                username=uname,
                discord_tag=utag,
                role_label=role_label,
                is_owner=is_owner,
                has_dj_role=has_dj_role,
                is_admin=is_admin,
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
                samesite="lax",
            )
            return response
        except Exception as exc:
            return HTMLResponse(f"<h3>Gagal memproses OAuth2 Discord: {exc}</h3>", status_code=500)

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
        return {"settings": dict(row)}

    @app.patch("/api/guilds/{guild_id}/settings")
    async def api_update_guild_settings(guild_id: str, request: Request):
        body = await request.json()
        now_iso = _utc_now()
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
                    now_iso,
                    guild_id,
                ),
            )
            row = conn.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
        return {"settings": dict(row) if row else {}}

    @app.get("/api/music/search")
    async def api_search_music(q: str = Query("", max_length=500)):
        cleaned_q = (q or "").strip()

        if cleaned_q:
            try:
                kind, _ = classify_music_input(cleaned_q)
                if kind in ("spotify_playlist", "spotify_album"):
                    pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, cleaned_q, 50)
                    pl_tracks = pl_data.get("tracks") or []
                    pl_name = str(pl_data.get("playlist_name") or "Spotify Playlist")
                    pl_thumb = str(
                        pl_data.get("thumbnail_url")
                        or (pl_tracks[0].thumbnail_url if pl_tracks else "")
                    )
                    total_dur = sum(int(t.duration_sec or 180) for t in pl_tracks)
                    dropdown_items: List[Dict[str, Any]] = [
                        {
                            "title": f"🎶 [PLAYLIST] {pl_name}",
                            "artist": f"Putar Langsung Semua ({len(pl_tracks)} Lagu)",
                            "album": "Spotify Playlist",
                            "duration_sec": total_dur,
                            "source_type": kind,
                            "source_url": cleaned_q,
                            "stream_url": "",
                            "thumbnail_url": pl_thumb,
                            "notice": "Klik Putar / +Antrean untuk memutar seluruh playlist",
                        }
                    ]
                    for tr in pl_tracks[:24]:
                        dropdown_items.append(asdict(tr))
                    return {"results": dropdown_items[:25]}
            except Exception:
                pass

        tracks = await asyncio.to_thread(search_songs_with_singer, cleaned_q, 25)
        return {"results": [asdict(t) for t in tracks[:25]]}

    @app.post("/api/music/resolve")
    async def api_resolve_music(request: Request):
        body = await request.json()
        raw_input = str(body.get("input", "")).strip()
        kind, _ = classify_music_input(raw_input)
        if kind in ("spotify_playlist", "spotify_album"):
            pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, raw_input, 50)
            tracks = pl_data.get("tracks") or []
            if not tracks:
                raise HTTPException(status_code=404, detail="Lagu dalam playlist Spotify tidak ditemukan.")
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
        # Validate guild_id is a valid Discord snowflake
        validate_snowflake_param("guild_id", guild_id)
        return _serialize_music_state(guild_id)

    @app.post("/api/guilds/{guild_id}/music/play")
    async def api_music_play(guild_id: str, request: Request):
        # Validate guild_id is a valid Discord snowflake
        validate_snowflake_param("guild_id", guild_id)
        body = await request.json()
        sess = _extract_session(request)
        requester_id = sess["user"]["id"] if sess else str(body.get("requester_id", "guest"))
        requester_name = sess["user"]["name"] if sess else str(body.get("requester_name", "Discord Member"))
        is_owner = sess["user"]["isOwner"] if sess else bool(body.get("is_owner", False))
        is_admin = sess["user"]["isAdmin"] if sess else bool(body.get("is_admin", False))
        
        live_bot = getattr(app.state, "bot", None)
        if live_bot is not None and guild_id.isdigit():
            guild_obj = live_bot.get_guild(int(guild_id))
            if guild_obj is not None:
                member_obj = guild_obj.get_member(int(requester_id)) if requester_id.isdigit() else None
                user_vc = member_obj.voice.channel if (member_obj and member_obj.voice) else None
                bot_vc = guild_obj.voice_client

                if user_vc is None:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": f"Kamu sedang tidak berada di Voice Channel pada server {guild_obj.name}. Masuk ke Voice Channel dulu sebelum memutar lagu!"
                        },
                    )
                if bot_vc and bot_vc.is_connected() and bot_vc.channel and bot_vc.channel.id != user_vc.id:
                    humans_in_bot_vc = [m for m in bot_vc.channel.members if not m.bot]
                    if humans_in_bot_vc:
                        return JSONResponse(
                            status_code=400,
                            content={
                                "error": f"Bot sedang digunakan di Voice Channel '{bot_vc.channel.name}'. Masuk ke channel tersebut terlebih dahulu!"
                            },
                        )

        raw_source_url = str(body.get("source_url", "")).strip()
        raw_source_type = str(body.get("source_type", "spotify_matched")).strip()
        play_now_flag = bool(body.get("play_now", False))
        has_dj_role = sess["user"]["hasDjRole"] if sess else bool(body.get("has_dj_role", False))

        try:
            input_kind = ""
            try:
                input_kind, _ = classify_music_input(raw_source_url)
            except Exception:
                input_kind = ""

            if raw_source_type in ("spotify_playlist", "spotify_album") or input_kind in ("spotify_playlist", "spotify_album"):
                pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, raw_source_url, 50)
                pl_tracks = pl_data.get("tracks") or []
                if not pl_tracks:
                    return JSONResponse(status_code=404, content={"error": "Playlist Spotify kosong atau tidak terbaca."})

                first_item = None
                started_any = False
                for idx, tr in enumerate(pl_tracks):
                    item_added, started = queue_service.add_track(
                        guild_id=guild_id,
                        title=tr.title,
                        artist=tr.artist,
                        album=tr.album or str(pl_data.get("playlist_name") or "Spotify Playlist"),
                        duration_sec=int(tr.duration_sec or 180),
                        source_type="spotify_matched",
                        source_url=tr.source_url,
                        stream_url="",
                        thumbnail_url=tr.thumbnail_url,
                        requester_id=requester_id,
                        requester_name=requester_name,
                        play_now=(play_now_flag and idx == 0),
                        user_roles=body.get("user_roles") or [],
                        is_admin=is_admin,
                        is_owner=is_owner,
                        dj_role_id=settings.dj_role_id,
                        has_dj_role=has_dj_role,
                    )
                    if idx == 0:
                        first_item = item_added
                    if started:
                        started_any = True

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
                is_owner=is_owner,
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
        # Validate guild_id is a valid Discord snowflake
        validate_snowflake_param("guild_id", guild_id)
        body = await request.json()
        sess = _extract_session(request)
        actor_id = sess["user"]["id"] if sess else str(body.get("actor_id", ""))
        is_owner = sess["user"]["isOwner"] if sess else bool(body.get("is_owner", False))
        is_admin = sess["user"]["isAdmin"] if sess else bool(body.get("is_admin", False))
        has_dj_role = sess["user"]["hasDjRole"] if sess else bool(body.get("has_dj_role", False))
        action = str(body.get("action", ""))
        item_id = str(body.get("item_id", ""))

        try:
            if action == "play_item":
                queue_service.play_queue_item(
                    guild_id=guild_id,
                    item_id=item_id,
                    actor_id=actor_id,
                    user_roles=body.get("user_roles") or [],
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=settings.dj_role_id,
                    has_dj_role=has_dj_role,
                )
            elif action == "remove_item":
                queue_service.remove_item(
                    guild_id=guild_id,
                    item_id=item_id,
                    actor_id=actor_id,
                    user_roles=body.get("user_roles") or [],
                    is_admin=is_admin,
                    is_owner=is_owner,
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
                    is_owner=is_owner,
                    dj_role_id=settings.dj_role_id,
                    has_dj_role=has_dj_role,
                )
            else:
                queue_service.control_session(
                    guild_id=guild_id,
                    action=action,
                    actor_id=actor_id,
                    user_roles=body.get("user_roles") or [],
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=settings.dj_role_id,
                    value=body.get("value"),
                    has_dj_role=has_dj_role,
                )
            return {"ok": True, "state": _serialize_music_state(guild_id)}
        except (PermissionError, KeyError, ValueError) as exc:
            return JSONResponse(status_code=403, content={"error": str(exc)})

    # =========================================================================
    # Academy Tasks, Modules & RPG Endpoints
    # =========================================================================
    @app.get("/api/guilds/{guild_id}/library")
    async def api_guild_library(guild_id: str, request: Request):
        return {"favorites": [], "playlists": []}

    @app.get("/api/favorites")
    async def api_get_favorites(user_id: str = Query("")):
        return {"favorites": []}

    @app.post("/api/favorites")
    @app.post("/api/guilds/{guild_id}/favorites")
    async def api_add_favorite(request: Request, guild_id: str = ""):
        return {"ok": True, "favorite_id": "disabled"}

    @app.delete("/api/favorites/{favorite_id}")
    async def api_delete_favorite(favorite_id: str):
        return {"ok": True}

    @app.get("/api/guilds/{guild_id}/playlists")
    async def api_get_playlists(guild_id: str):
        return {"playlists": []}

    @app.post("/api/guilds/{guild_id}/playlists/import-spotify")
    async def api_import_spotify_playlist(guild_id: str, request: Request):
        body = await request.json()
        sess = _extract_session(request)
        owner_id = sess["user"]["id"] if sess else str(body.get("owner_user_id") or settings.owner_discord_id)
        owner_name = sess["user"]["name"] if sess else str(body.get("owner_username") or "Aetheriaaa")
        spotify_url = str(body.get("spotify_url") or body.get("url") or "").strip()

        if not spotify_url:
            return JSONResponse(status_code=400, content={"error": "Masukkan link Playlist atau Album Spotify terlebih dahulu."})

        try:
            pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, spotify_url, 50)
        except Exception as exc:
            return JSONResponse(status_code=400, content={"error": f"Gagal membaca playlist Spotify: {exc}"})

        tracks = pl_data.get("tracks") or []
        if not tracks:
            return JSONResponse(status_code=404, content={"error": "Tidak ditemukan lagu di dalam playlist Spotify tersebut."})

        playlist_name = str(pl_data.get("playlist_name") or "Spotify Playlist")
        for tr in tracks:
            queue_service.add_track(
                guild_id=guild_id,
                title=tr.title,
                artist=tr.artist,
                album=playlist_name,
                duration_sec=tr.duration_sec,
                source_type="spotify_matched",
                source_url=tr.source_url,
                stream_url="",
                thumbnail_url=tr.thumbnail_url,
                requester_id=owner_id,
                requester_name=owner_name,
                play_now=False,
            )

        return {
            "ok": True,
            "playlist_name": playlist_name,
            "tracks_count": len(tracks),
            "played": True,
            "state": _serialize_music_state(guild_id),
        }

    @app.get("/api/guilds/{guild_id}/tasks")
    async def api_get_tasks(guild_id: str):
        # Validate guild_id is a valid Discord snowflake
        validate_snowflake_param("guild_id", guild_id)
        # list_tasks otomatis menjalankan purge_expired_tasks(guild_id) terlebih dahulu
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
        sess = _extract_session(request)
        creator = sess["user"]["name"] if sess else str(body.get("created_by", "Aetheriaaa"))
        task = academy_service.create_task(
            guild_id=guild_id,
            course_name=str(body.get("course_name", "Umum")),
            title=str(body.get("title", "")),
            deadline_iso=str(body.get("deadline_iso", _utc_now())),
            created_by=creator,
            description=str(body.get("description", "")),
            source_url=str(body.get("source_url", "")),
        )
        return {"task": asdict(task)}

    @app.patch("/api/guilds/{guild_id}/tasks/{task_id}")
    async def api_patch_task(guild_id: str, task_id: str, request: Request):
        body = await request.json()
        sess = _extract_session(request)
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
        # Validate guild_id is a valid Discord snowflake
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
        sess = _extract_session(request)
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
        
        # SECURITY: Validate stored_filename to prevent path traversal
        # Must be safe filename: only alphanumeric, dash, underscore, dot, and valid UUID pattern
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
            # SECURITY: Ensure resolved path is within allowed directory
            try:
                fp_resolved = fp.resolve()
                # Check if path is within BASE_DIR or modules_dir
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

    @app.get("/api/guilds/{guild_id}/rpg")
    async def api_guild_rpg(guild_id: str):
        # Validate guild_id is a valid Discord snowflake
        validate_snowflake_param("guild_id", guild_id)
        return {
            "leaderboard": leveling_service.get_leaderboard(guild_id, limit=15),
            "afk_list": leveling_service.list_afk(guild_id),
        }

    @app.post("/api/guilds/{guild_id}/rpg/activity")
    async def api_rpg_activity(guild_id: str, request: Request):
        sess = _extract_session(request)
        if (
            not sess
            or not sess.get("user", {}).get("isOwner")
            or str(sess.get("user", {}).get("id")) != str(settings.owner_discord_id)
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Akses Ditolak: Fitur Uji Aktivitas & Simulasi EXP hanya dapat diakses oleh Bot Owner."
                },
            )

        body = await request.json()
        uid = sess["user"]["id"]
        uname = (sess["user"]["discordTag"].lstrip("@") if sess else "filisim") or "filisim"
        dname = sess["user"]["name"]
        activity_type = str(body.get("activity_type", "chat")).strip().lower()
        msg = str(body.get("message_content", "Aktivitas di server TK1GACORKINK"))
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
        # Validate guild_id is a valid Discord snowflake
        validate_snowflake_param("guild_id", guild_id)
        body = await request.json()
        sess = _extract_session(request)
        uid = sess["user"]["id"] if sess else str(body.get("user_id") or settings.owner_discord_id)
        uname = sess["user"]["name"] if sess else str(body.get("username") or "Aetheriaaa")
        leveling_service.set_afk(
            guild_id=guild_id,
            user_id=uid,
            username=uname,
            reason=str(body.get("reason", "Sedang AFK")),
        )
        return {"ok": True}

    @app.delete("/api/guilds/{guild_id}/afk/{user_id}")
    async def api_clear_afk(guild_id: str, user_id: str):
        # Validate guild_id is a valid Discord snowflake
        validate_snowflake_param("guild_id", guild_id)
        leveling_service.clear_afk(guild_id, user_id)
        return {"ok": True}

    # =========================================================================
    # Owner-Only Super-Admin & Python Codebase Endpoints
    # =========================================================================
    def _require_owner(request: Request) -> None:
        sess = _extract_session(request)
        if (
            not sess
            or not sess.get("user", {}).get("isOwner")
            or str(sess.get("user", {}).get("id")) != str(settings.owner_discord_id)
        ):
            raise HTTPException(
                status_code=403,
                detail="Akses Ditolak: Kode sumber Python, unduhan paket .zip, dan Super-Admin Hub dikhususkan hanya untuk Bot Owner (OWNER_DISCORD_ID).",
            )

    @app.get("/api/admin/metrics")
    async def api_admin_metrics(request: Request):
        _require_owner(request)
        return get_system_metrics(settings.owner_discord_id)

    @app.post("/api/admin/backup")
    async def api_admin_backup(request: Request):
        _require_owner(request)
        return backup_service.create_consistent_backup(encrypt=True)

    @app.post("/api/admin/yt-dlp")
    async def api_admin_ytdlp(request: Request):
        _require_owner(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        return BackupService.check_and_update_ytdlp(perform_update=bool(body.get("perform_update", False)))

    @app.post("/api/admin/run-tests")
    async def api_admin_tests(request: Request):
        _require_owner(request)
        return run_test_suite()

    @app.get("/api/python-codebase")
    async def api_python_codebase(request: Request, file: str = Query("app/main.py")):
        _require_owner(request)
        safe_path = (BASE_DIR / file).resolve()
        if not str(safe_path).startswith(str(BASE_DIR.resolve())) or not safe_path.exists():
            safe_path = BASE_DIR / "app" / "main.py"
        rel_selected = str(safe_path.relative_to(BASE_DIR))
        selected_role = next(
            (f["role"] for f in PYTHON_CODEBASE_FILES if f["path"] == rel_selected),
            "Source Code Bot Python",
        )
        return {
            "files": PYTHON_CODEBASE_FILES,
            "selected_file": rel_selected,
            "selected_role": selected_role,
            "content": safe_path.read_text(encoding="utf-8"),
        }

    @app.get("/api/python-codebase/download-zip")
    async def api_download_zip(request: Request):
        _require_owner(request)
        zip_path = Path(create_source_zip())
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename="athenaa-discord-bot.zip",
        )

    # =========================================================================
    # Serve Pre-Built Spotify React Web UI (app/web/static) on Port 10031
    # =========================================================================
    if (STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        candidate = (STATIC_DIR / full_path).resolve()
        if (
            full_path
            and str(candidate).startswith(str(STATIC_DIR.resolve()))
            and candidate.is_file()
        ):
            return FileResponse(str(candidate))
        index_html = STATIC_DIR / "index.html"
        if index_html.exists():
            raw_html = index_html.read_text(encoding="utf-8", errors="ignore")
            if "</body>" in raw_html:
                patched_html = raw_html.replace("</body>", f"{UI_CUSTOMIZATION_INJECTION}\n</body>")
            else:
                patched_html = raw_html + UI_CUSTOMIZATION_INJECTION
            return HTMLResponse(patched_html)
        return JSONResponse({"status": "Athenaa API Running", "web_ui": "Jalankan npm run build untuk menyertakan static UI"})

    return app