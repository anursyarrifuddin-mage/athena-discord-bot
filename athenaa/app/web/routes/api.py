"""
Modul FastAPI REST API, WebSocket (/ws), Discord OAuth2 Multi-Device Auth (Maks. 5 Sesi),
Audio Stream Proxy Anti-CORS (/api/guilds/{guild_id}/music/stream), dan Static SPA Hosting
untuk Athenaa Web Dashboard (Pterodactyl Port 10031 / bot.athenaa.my.id).
Menyinkronkan kondisi asli Discord Bot VoiceClient dengan Web Player secara real-time.
"""

import asyncio
import base64
import json
import os
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Union

from pydantic import BaseModel, Field

try:
    from pydantic import field_validator as _pydantic_field_validator  # type: ignore

    PYDANTIC_V2 = True
except ImportError:
    from pydantic import validator as _pydantic_validator  # type: ignore

    PYDANTIC_V2 = False


def compat_field_validator(*fields: str, mode: str = "before"):
    """Shim kompatibilitas validator untuk Pydantic v1 dan Pydantic v2."""
    if PYDANTIC_V2:
        return _pydantic_field_validator(*fields, mode=mode)
    return _pydantic_validator(*fields, pre=(mode == "before"), allow_reuse=True)


class CompatBaseModel(BaseModel):
    """BaseModel dengan dukungan .model_validate() di Pydantic v1 maupun v2."""

    @classmethod
    def model_validate(cls, obj: Any, *args: Any, **kwargs: Any):
        if PYDANTIC_V2 and hasattr(super(), "model_validate"):
            return super().model_validate(obj, *args, **kwargs)  # type: ignore
        return cls.parse_obj(obj)


try:
    from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status  # type: ignore
    from fastapi.middleware.cors import CORSMiddleware  # type: ignore
    from fastapi.responses import (  # type: ignore
        FileResponse,
        HTMLResponse,
        JSONResponse,
        PlainTextResponse,
        RedirectResponse,
        Response,
        StreamingResponse,
    )
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # type: ignore
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
    Response = Any  # type: ignore
    StreamingResponse = Any  # type: ignore
    StaticFiles = Any  # type: ignore
    Depends = Any  # type: ignore
    status = Any  # type: ignore
    HTTPBearer = Any  # type: ignore
    HTTPAuthorizationCredentials = Any  # type: ignore

    def Query(default: Any = None, **_kwargs: Any) -> Any:  # type: ignore
        return default

from app.cli_bridge import create_source_zip, run_test_suite
from app.config import BASE_DIR, settings
from app.database import db_manager
from app.security.validators import (
    SlidingWindowRateLimiter,
    sanitize_and_validate_attachment,
)
from app.services.academy_service import AcademyService
from app.services.backup_service import BackupService
from app.services.leveling_service import LevelingService
from app.services.lyrics_service import lyrics_service
from app.services.music_service import (
    DEFAULT_STREAM_USER_AGENT,
    VERIFIED_RADIO_STATIONS,
    YOUTUBE_URL_RE,
    classify_music_input,
    extract_playable_stream_ytdlp,
    extract_spotify_playlist_tracks,
    resolve_direct_youtube_video_link,
    resolve_spotify_link,
    search_songs_with_singer,
)
from app.services.queue_service import GuildQueueState, queue_service

START_TIME = time.time()
MAX_SESSIONS_PER_USER = 5
rate_limiter = SlidingWindowRateLimiter(max_requests=1000, window_seconds=60)
academy_service = AcademyService()
leveling_service = LevelingService()
backup_service = BackupService()

STATIC_DIR = BASE_DIR / "app" / "web" / "static"

PYTHON_CODEBASE_FILES: List[Dict[str, str]] = []

UI_CUSTOMIZATION_INJECTION = r"""
<style id="athenaa-ui-patch-styles">
  div.max-h-72,
  div.max-h-\[340px\] {
    max-height: 560px !important;
  }
  a[download*="athenaa-discord-bot.zip"],
  a[href*="/api/python-codebase"],
  button[title*="Inspeksi Kode Sumber Python"],
  button[title*="Unduh Paket Bot"],
  button[aria-label*="Simpan ke favorit"],
  button[aria-label*="Favorit"] {
    display: none !important;
  }
</style>
<script id="athenaa-ui-patch-script">
(function() {
  var FORBIDDEN_LABELS = [
    'favorit & playlist',
    'koleksi lagu & playlist',
    'super-admin hub',
    'super-admin & kode python',
    'khusus owner · paket deploy .zip',
    'kode bot python',
    'source /athenaa & paket .zip',
    '</> kode python',
    'kode python',
    'unduh bot (.zip)'
  ];

  function shouldHideNode(text) {
    if (!text) return false;
    var low = text.trim().toLowerCase();
    for (var i = 0; i < FORBIDDEN_LABELS.length; i++) {
      if (low === FORBIDDEN_LABELS[i] || low.indexOf(FORBIDDEN_LABELS[i]) !== -1) {
        return true;
      }
    }
    return false;
  }


  var _lastSettingsGuildId = '';
  function mountKoyaCarlSettingsPanel() {
    try {
      var headings = document.querySelectorAll('h2');
      var settingsHeading = null;
      for (var i = 0; i < headings.length; i++) {
        if ((headings[i].textContent || '').indexOf('Pengaturan Multi-Guild Server') !== -1) {
          settingsHeading = headings[i];
          break;
        }
      }
      if (!settingsHeading) return;
      var container = settingsHeading.closest('div.bg-\\[\\#181818\\]') || settingsHeading.parentElement.parentElement;
      if (!container) return;
      container.style.maxWidth = '64rem';

      var srvSelect = document.querySelector('select[aria-label="Pilih Server Discord"]');
      var currentGuildId = srvSelect ? srvSelect.value : '1428666546942902294';

      var existingPanel = document.getElementById('athenaa-koya-carl-suite');
      if (existingPanel && _lastSettingsGuildId === currentGuildId) {
        return;
      }
      if (existingPanel) {
        existingPanel.remove();
      }
      _lastSettingsGuildId = currentGuildId;

      var suiteDiv = document.createElement('div');
      suiteDiv.id = 'athenaa-koya-carl-suite';
      suiteDiv.className = 'mt-6 pt-6 border-t border-white/10 space-y-5';
      suiteDiv.innerHTML = [
        '<div class="flex items-center justify-between flex-wrap gap-2">',
        '  <div>',
        '    <h3 class="text-sm font-bold text-[#DC95FF]">🛡️ Modul Koya, Carl-bot, AutoMod Chat Sensor & AI Assistant</h3>',
        '    <p class="text-xs text-[#B3B3B3]">Konfigurasi fitur moderasi otomatis, sapaan member baru, auto-role, dan AI Chatbot hemat RAM.</p>',
        '  </div>',
        '  <span class="px-2.5 py-1 rounded-full bg-emerald-500/15 border border-emerald-400/30 text-[11px] font-semibold text-emerald-300">⚡ Zero RAM Overhead Mode</span>',
        '</div>',
        '<div class="grid grid-cols-1 md:grid-cols-2 gap-4">',
        '  <div class="bg-[#202020] border border-white/10 rounded-xl p-4 space-y-3">',
        '    <div class="text-xs font-bold text-white">🤖 1. AI Chatbot (@Athena) & Info Lagu Berikutnya</div>',
        '    <label class="flex items-center gap-2 text-xs text-white/90 cursor-pointer">',
        '      <input type="checkbox" id="cfg_announce_next_track" checked class="accent-[#DC95FF] w-4 h-4" />',
        '      <span>Kirim info teks/Embed otomatis di Discord saat berganti ke lagu berikutnya</span>',
        '    </label>',
        '    <label class="flex items-center gap-2 text-xs text-white/90 cursor-pointer">',
        '      <input type="checkbox" id="cfg_ai_chat_enabled" checked class="accent-[#DC95FF] w-4 h-4" />',
        '      <span>Aktifkan AI Chatbot (Berita Online) & Perintah Musik Teks saat @Athena di-tag</span>',
        '    </label>',
        '  </div>',
        '  <div class="bg-[#202020] border border-white/10 rounded-xl p-4 space-y-3">',
        '    <div class="text-xs font-bold text-white">🛡️ 2. AutoMod & Chat Sensor (Gaya Carl-bot)</div>',
        '    <label class="flex items-center gap-2 text-xs text-white/90 cursor-pointer">',
        '      <input type="checkbox" id="cfg_automod_badwords_enabled" class="accent-[#DC95FF] w-4 h-4" />',
        '      <span>Sensor & hapus otomatis kata kasar / promosi judol / toxic</span>',
        '    </label>',
        '    <label class="flex items-center gap-2 text-xs text-white/90 cursor-pointer">',
        '      <input type="checkbox" id="cfg_automod_antilink_enabled" class="accent-[#DC95FF] w-4 h-4" />',
        '      <span>Blokir link invite Discord luar (discord.gg/) & tautan mencurigakan</span>',
        '    </label>',
        '    <label class="flex items-center gap-2 text-xs text-white/90 cursor-pointer">',
        '      <input type="checkbox" id="cfg_automod_antispam_enabled" class="accent-[#DC95FF] w-4 h-4" />',
        '      <span>Proteksi Anti-Spam Mass Mention (>5 tag) & Caps Lock berlebihan</span>',
        '    </label>',
        '    <div>',
        '      <label class="block text-[11px] text-[#B3B3B3] mb-1">Daftar Kata Sensor Kustom (pisahkan dengan koma)</label>',
        '      <input type="text" id="cfg_automod_badwords_list" placeholder="slot gacor,judol,depo pulsa,maxwin" class="w-full bg-[#161616] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white font-mono" />',
        '    </div>',
        '  </div>',
        '  <div class="bg-[#202020] border border-white/10 rounded-xl p-4 space-y-3">',
        '    <div class="text-xs font-bold text-white">👋 3. Welcome, Goodbye & Auto-Role (Gaya Koya Bot)</div>',
        '    <label class="flex items-center gap-2 text-xs text-white/90 cursor-pointer">',
        '      <input type="checkbox" id="cfg_welcome_enabled" class="accent-[#DC95FF] w-4 h-4" />',
        '      <span>Kirim kartu Embed sambutan saat member baru join server</span>',
        '    </label>',
        '    <div>',
        '      <label class="block text-[11px] text-[#B3B3B3] mb-1">ID Channel Welcome Discord</label>',
        '      <input type="text" id="cfg_welcome_channel_id" placeholder="Contoh: 1428666547701809159" class="w-full bg-[#161616] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white font-mono" />',
        '    </div>',
        '    <div>',
        '      <label class="block text-[11px] text-[#B3B3B3] mb-1">Pesan Welcome ({user}, {server}, {count})</label>',
        '      <input type="text" id="cfg_welcome_message" placeholder="Selamat datang {user} di {server}! (Member #{count})" class="w-full bg-[#161616] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white" />',
        '    </div>',
        '    <div>',
        '      <label class="block text-[11px] text-[#B3B3B3] mb-1">ID Auto-Role Member Baru (Otomatis diberikan saat join)</label>',
        '      <input type="text" id="cfg_autorole_id" placeholder="Masukkan Role ID Discord" class="w-full bg-[#161616] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white font-mono" />',
        '    </div>',
        '  </div>',
        '  <div class="bg-[#202020] border border-white/10 rounded-xl p-4 space-y-3">',
        '    <div class="text-xs font-bold text-white">📋 4. Goodbye & Channel Mod-Log Server</div>',
        '    <label class="flex items-center gap-2 text-xs text-white/90 cursor-pointer">',
        '      <input type="checkbox" id="cfg_goodbye_enabled" class="accent-[#DC95FF] w-4 h-4" />',
        '      <span>Kirim pesan saat ada member keluar dari server</span>',
        '    </label>',
        '    <div>',
        '      <label class="block text-[11px] text-[#B3B3B3] mb-1">Pesan Goodbye ({user}, {server})</label>',
        '      <input type="text" id="cfg_goodbye_message" placeholder="Sampai jumpa {user}, terima kasih sudah bergabung di {server}." class="w-full bg-[#161616] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white" />',
        '    </div>',
        '    <div>',
        '      <label class="block text-[11px] text-[#B3B3B3] mb-1">ID Channel Mod-Log (Log Sensor AutoMod & Aktivitas)</label>',
        '      <input type="text" id="cfg_modlog_channel_id" placeholder="Contoh: 1558142572164022362" class="w-full bg-[#161616] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white font-mono" />',
        '    </div>',
        '    <div class="pt-2">',
        '      <button type="button" id="btn_save_koya_carl" class="w-full py-2 px-4 rounded-full bg-[#DC95FF] hover:bg-[#FFBEFB] text-black font-bold text-xs transition-colors">💾 Simpan Modul AutoMod, Welcome & AI</button>',
        '      <div id="koya_carl_save_status" class="text-[11px] text-emerald-400 mt-1.5 hidden">✅ Pengaturan Koya, Carl-bot & AI berhasil disimpan!</div>',
        '    </div>',
        '  </div>',
        '</div>'
      ].join('\n');

      container.appendChild(suiteDiv);

      fetch('/api/guilds/' + encodeURIComponent(currentGuildId) + '/settings')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          var s = (data && data.settings) || {};
          var setChk = function(id, val, defVal) {
            var el = document.getElementById(id);
            if (el) el.checked = (val !== undefined && val !== null) ? Boolean(Number(val)) : defVal;
          };
          var setVal = function(id, val, defVal) {
            var el = document.getElementById(id);
            if (el) el.value = (val !== undefined && val !== null && val !== '') ? String(val) : defVal;
          };
          setChk('cfg_announce_next_track', s.announce_next_track, true);
          setChk('cfg_ai_chat_enabled', s.ai_chat_enabled, true);
          setChk('cfg_automod_badwords_enabled', s.automod_badwords_enabled, false);
          setChk('cfg_automod_antilink_enabled', s.automod_antilink_enabled, false);
          setChk('cfg_automod_antispam_enabled', s.automod_antispam_enabled, false);
          setVal('cfg_automod_badwords_list', s.automod_badwords_list, 'slot gacor,judol,depo pulsa,maxwin');
          setChk('cfg_welcome_enabled', s.welcome_enabled, false);
          setVal('cfg_welcome_channel_id', s.welcome_channel_id, '');
          setVal('cfg_welcome_message', s.welcome_message, 'Selamat datang {user} di **{server}**! Semoga betah ya (Member #{count}).');
          setVal('cfg_autorole_id', s.autorole_id, '');
          setChk('cfg_goodbye_enabled', s.goodbye_enabled, false);
          setVal('cfg_goodbye_message', s.goodbye_message, 'Sampai jumpa **{user}**, terima kasih sudah bergabung di {server}.');
          setVal('cfg_modlog_channel_id', s.modlog_channel_id, '');
        })
        .catch(function() {});

      var saveBtn = document.getElementById('btn_save_koya_carl');
      if (saveBtn) {
        saveBtn.addEventListener('click', function() {
          var gChk = function(id) { var e = document.getElementById(id); return e && e.checked ? 1 : 0; };
          var gVal = function(id) { var e = document.getElementById(id); return e ? e.value.trim() : ''; };
          var payload = {
            announce_next_track: gChk('cfg_announce_next_track'),
            ai_chat_enabled: gChk('cfg_ai_chat_enabled'),
            automod_badwords_enabled: gChk('cfg_automod_badwords_enabled'),
            automod_antilink_enabled: gChk('cfg_automod_antilink_enabled'),
            automod_antispam_enabled: gChk('cfg_automod_antispam_enabled'),
            automod_badwords_list: gVal('cfg_automod_badwords_list'),
            welcome_enabled: gChk('cfg_welcome_enabled'),
            welcome_channel_id: gVal('cfg_welcome_channel_id'),
            welcome_message: gVal('cfg_welcome_message'),
            autorole_id: gVal('cfg_autorole_id'),
            goodbye_enabled: gChk('cfg_goodbye_enabled'),
            goodbye_message: gVal('cfg_goodbye_message'),
            modlog_channel_id: gVal('cfg_modlog_channel_id')
          };
          fetch('/api/guilds/' + encodeURIComponent(currentGuildId) + '/settings', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          }).then(function(r) {
            if (r.ok) {
              var st = document.getElementById('koya_carl_save_status');
              if (st) {
                st.classList.remove('hidden');
                setTimeout(function() { st.classList.add('hidden'); }, 4000);
              }
            }
          });
        });
      }
    } catch (err) {}
  }

  function applyAthenaaUiCleanup() {
    mountKoyaCarlSettingsPanel();
    try {
      var interactive = document.querySelectorAll('button, a, nav button, aside button');
      for (var i = 0; i < interactive.length; i++) {
        var el = interactive[i];
        var txt = (el.textContent || '').trim();
        if (txt.length > 0 && txt.length < 120 && shouldHideNode(txt)) {
          el.style.setProperty('display', 'none', 'important');
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
        var el2 = allParagraphs[k];
        if (el2.children.length === 0 || el2.tagName === 'BUTTON') {
          var t = (el2.textContent || '').trim();
          if (t === 'Keamanan Sesi Tunggal Discord OAuth2') {
            el2.textContent = 'Sinkronisasi Server Otomatis';
          } else if (t.indexOf('Login manual menggunakan User ID telah dinonaktifkan') !== -1) {
            el2.textContent = 'Role dan akses diverifikasi langsung dari server Discord (Maks. 5 perangkat aktif).';
          } else if (t === 'Authorize dengan Discord OAuth2 Resmi') {
            el2.textContent = 'Login dengan Discord';
          } else if (t === 'Buka Otorisasi Discord via Jendela Popup') {
            el2.textContent = 'Login via Popup';
          } else if (t.indexOf('20261-[') !== -1 || t.indexOf('-[25S1') !== -1) {
            el2.textContent = t
              .replace(/\d+-\[([A-Za-z0-9]+)-Pemrogr\(([^)]+)\)\]-[A-Za-z0-9]+/g, 'Pemrograman ($2) · Kelas $1')
              .replace(/\d+-\[([A-Za-z0-9]+)-Elektro\(([^)]+)\)\]-[A-Za-z0-9]+/g, 'Elektronika ($2) · Kelas $1')
              .replace(/\d+-\[([A-Za-z0-9]+)-([^(\]\-]+)\(([^)]+)\)\]-[A-Za-z0-9]+/g, '$2 ($3) · Kelas $1')
              .replace('Sumber: moodle_ics', 'Sumber: Waskita LMS');
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


def _build_valid_pdf_bytes(filename: str, uploader: str, context: str) -> bytes:
    """Generate a minimal valid PDF for fallback/testing."""
    safe_title = (filename or "Modul Akademik").replace("(", "[").replace(")", "]")
    safe_up = (uploader or "Aetheriaaa").replace("(", "[").replace(")", "]")
    safe_ctx = (context or "att").replace("(", "[").replace(")", "]")
    stream_text = (
        "BT\n"
        "/F1 16 Tf\n"
        "50 760 Td\n"
        f"({safe_title}) Tj\n"
        "/F1 11 Tf\n"
        "0 -28 Td\n"
        f"(Diunggah oleh: {safe_up} | ID Lampiran: {safe_ctx}) Tj\n"
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


def _ensure_multi_session_table() -> None:
    """Memastikan tabel discord_user_sessions tersedia dengan kolom is_owner, has_dj_role, dan is_admin."""
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
            for col_name, col_def in (
                ("is_owner", "INTEGER NOT NULL DEFAULT 0"),
                ("has_dj_role", "INTEGER NOT NULL DEFAULT 0"),
                ("is_admin", "INTEGER NOT NULL DEFAULT 0"),
                ("user_guild_ids", "TEXT DEFAULT ''"),
            ):
                try:
                    cols = {r[1] for r in conn.execute("PRAGMA table_info(discord_user_sessions)").fetchall()}
                    if col_name not in cols:
                        conn.execute(f"ALTER TABLE discord_user_sessions ADD COLUMN {col_name} {col_def}")
                except Exception:
                    pass
            try:
                cols_ds = {r[1] for r in conn.execute("PRAGMA table_info(discord_sessions)").fetchall()}
                if "user_guild_ids" not in cols_ds:
                    conn.execute("ALTER TABLE discord_sessions ADD COLUMN user_guild_ids TEXT DEFAULT ''")
            except Exception:
                pass
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_discord_user_sessions_uid ON discord_user_sessions(user_id, created_at ASC)"
            )
    except Exception:
        pass


_ensure_multi_session_table()


def _resolve_oauth_redirect_uri(request: Optional[Request] = None) -> str:
    """
    Menentukan Redirect URI OAuth2 secara presisi untuk bot.athenaa.my.id.
    Mengutamakan host dari request aktif apabila diakses melalui domain bot.athenaa.my.id,
    serta membersihkan spasi liar dari .env.
    """
    configured = (settings.discord_redirect_uri or "").strip()
    # Jika di .env masih tertulis athenaa.my.id lama (tanpa subdomain bot.), arahkan ke bot.athenaa.my.id
    if configured in ("https://athenaa.my.id/auth/callback", "http://athenaa.my.id/auth/callback"):
        configured = "https://bot.athenaa.my.id/auth/callback"

    if request is not None:
        try:
            fwd_host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
            fwd_proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
            if fwd_host and ("athenaa.my.id" in fwd_host or "localhost" in fwd_host or "127.0.0.1" in fwd_host):
                scheme = "https" if "athenaa.my.id" in fwd_host else fwd_proto
                return f"{scheme}://{fwd_host}/auth/callback"
        except Exception:
            pass

    return configured or "https://bot.athenaa.my.id/auth/callback"


# =========================================================================
# Security: Pydantic Models for Request Validation (Pydantic v1 & v2 Compatible)
# =========================================================================
class PlayMusicRequest(CompatBaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    artist: Optional[str] = Field(default="Unknown", max_length=500)
    album: Optional[str] = Field(default="", max_length=500)
    duration_sec: Optional[Union[int, float]] = Field(default=180, ge=0, le=86400)
    source_type: Optional[str] = Field(default="youtube", max_length=100)
    source_url: Optional[str] = Field(default="", max_length=4096)
    stream_url: Optional[str] = Field(default="", max_length=4096)
    thumbnail_url: Optional[str] = Field(default="", max_length=4096)
    play_now: Optional[bool] = False
    requester_id: Optional[str] = None
    requester_name: Optional[str] = None
    user_roles: Optional[List[str]] = None
    is_admin: Optional[bool] = None
    is_owner: Optional[bool] = None

    @compat_field_validator("artist", "album", "source_url", "stream_url", "thumbnail_url", "source_type", mode="before")
    @classmethod
    def coerce_none_to_str(cls, v: Any) -> str:
        return str(v or "")

    @compat_field_validator("duration_sec", mode="before")
    @classmethod
    def coerce_duration(cls, v: Any) -> int:
        try:
            return max(0, int(float(v or 0)))
        except (ValueError, TypeError):
            return 0


class ControlMusicRequest(CompatBaseModel):
    action: str = Field(..., min_length=1, max_length=50)
    item_id: Optional[str] = Field(default="")
    value: Optional[Union[int, float, str, bool]] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    user_roles: Optional[List[str]] = None
    is_admin: Optional[bool] = None
    is_owner: Optional[bool] = None

    @compat_field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, v: Any) -> str:
        return str(v or "").strip().lower()

    @compat_field_validator("item_id", mode="before")
    @classmethod
    def normalize_item_id(cls, v: Any) -> str:
        return str(v or "").strip()


class SpotifyPlaylistImportRequest(CompatBaseModel):
    spotify_url: Optional[str] = Field(default="", max_length=2048)
    url: Optional[str] = Field(default="", max_length=2048)
    name: Optional[str] = Field(default="", max_length=200)
    play_immediately: Optional[bool] = False
    queue_now: Optional[bool] = False
    owner_user_id: Optional[str] = None
    owner_username: Optional[str] = None


class TaskCreateRequest(CompatBaseModel):
    course_name: str = Field(default="Umum", max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    deadline_iso: str = Field(..., min_length=1)
    created_by: str = Field(default="Aetheriaaa", max_length=100)
    description: str = Field(default="", max_length=2000)
    source_url: str = Field(default="", max_length=2048)


class TaskPatchRequest(CompatBaseModel):
    is_completed: Optional[bool] = None
    actor_name: str = Field(default="Aetheriaaa", max_length=100)


class ModuleUploadRequest(CompatBaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    size_bytes: int = Field(..., ge=1, le=15 * 1024 * 1024)
    task_id: str = Field(default="", max_length=100)
    content_base64: Optional[str] = Field(default="")

    @compat_field_validator("filename", mode="before")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        v_str = str(v or "").strip()
        if ".." in v_str or "/" in v_str or "\\" in v_str:
            raise ValueError("Invalid filename: path traversal detected")
        ext = Path(v_str).suffix.lower()
        if ext not in {".pdf", ".doc", ".docx"}:
            raise ValueError("Only .pdf, .doc, .docx files allowed")
        return v_str


class GuildSettingsUpdateRequest(CompatBaseModel):
    music_channel_id: Optional[str] = None
    task_channel_id: Optional[str] = None
    dj_role_id: Optional[str] = None
    moodle_ics_url_encrypted: Optional[str] = None
    reminder_days_before: Optional[int] = Field(default=None, ge=0, le=30)
    timezone: Optional[str] = Field(default=None, max_length=50)
    exp_cooldown_seconds: Optional[int] = Field(default=None, ge=1, le=3600)


class AdminActionRequest(CompatBaseModel):
    guild_id: Optional[str] = Field(default="")


# =========================================================================
# Security: Rate Limiting & Audit Logging
# =========================================================================
async def rate_limit_dependency(request: Request):
    """Per-endpoint rate limiting based on session token or IP."""
    auth_header = request.headers.get("Authorization", "")
    session_token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
    if not session_token:
        session_token = request.query_params.get("session_token", "").strip()
    if not session_token:
        session_token = request.cookies.get("athenaa_session_token", "").strip()
    client_host = request.client.host if getattr(request, "client", None) else "unknown"
    key = f"rl:{session_token or client_host}"
    if not rate_limiter.allow(key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please slow down.")


def audit_log(action: str, user_id: str, guild_id: str = "", details: str = "", success: bool = True):
    timestamp = _utc_now()
    status_str = "SUCCESS" if success else "FAILED"
    log_entry = f"[AUDIT] {timestamp} | {action} | user={user_id} | guild={guild_id} | {status_str} | {details}"
    print(log_entry)


def _serialize_track_for_web(item: Any) -> Dict[str, Any]:
    """
    Serialisasi track untuk Web Player.
    PENTING: Untuk semua lagu non-radio (YouTube Music / Spotify Matched), `stream_url`
    diarahkan ke endpoint proxy internal `/api/guilds/{guild_id}/music/stream?item_id={item_id}`
    agar browser TIDAK PERNAH terkena blokir CORS atau IP-lock pada `googlevideo.com`!
    """
    raw_stream = str(getattr(item, "stream_url", "") or "")
    src_type = str(getattr(item, "source_type", "spotify_matched") or "spotify_matched")
    gid = str(getattr(item, "guild_id", "") or settings.main_guild_id)
    item_id = str(getattr(item, "item_id", "") or getattr(item, "id", "") or "")

    # Web Dashboard hanya berfungsi sebagai Remote Control untuk Bot Discord (audio keluar di Discord Voice)
    safe_web_stream = ""

    return {
        "item_id": item_id,
        "guild_id": gid,
        "position": getattr(item, "position", 1),
        "title": getattr(item, "title", ""),
        "artist": getattr(item, "artist", ""),
        "album": getattr(item, "album", ""),
        "duration_sec": getattr(item, "duration_sec", 0),
        "source_type": src_type,
        "source_url": getattr(item, "source_url", ""),
        "stream_url": safe_web_stream,
        "direct_stream_url": raw_stream if src_type == "radio" else "",
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
    is_admin: bool,
    is_owner: Optional[bool] = None,
    has_dj_role: Optional[bool] = None,
    user_guild_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Menerbitkan token sesi untuk akun Discord dengan batas maksimal 5 perangkat/sesi aktif.
    Mendukung penuh atribut `isOwner`, `hasDjRole`, dan `isAdmin`.
    """
    _ensure_multi_session_table()
    uid_str = str(user_id or "").strip()
    resolved_owner = bool(is_owner) if is_owner is not None else (uid_str == str(settings.owner_discord_id or ""))
    resolved_admin = bool(is_admin) or resolved_owner
    resolved_dj = bool(has_dj_role) if has_dj_role is not None else resolved_admin

    new_token = f"athenaa_sess_{uid_str}_{secrets.token_hex(12)}"
    now_iso = _utc_now()
    oldest_evicted = False

    with db_manager.transaction() as conn:
        legacy_row = conn.execute(
            "SELECT * FROM discord_sessions WHERE user_id = ?",
            (uid_str,),
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
                    int(legacy_row["is_owner"]) if "is_owner" in legacy_row.keys() else (1 if resolved_owner else 0),
                    int(legacy_row["has_dj_role"]) if "has_dj_role" in legacy_row.keys() else (1 if resolved_dj else 0),
                    int(legacy_row["is_admin"]),
                    legacy_row["created_at"],
                ),
            )

        conn.execute(
            """
            INSERT INTO discord_user_sessions (
                session_token, user_id, username, discord_tag, role_label,
                is_owner, has_dj_role, is_admin, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_token,
                uid_str,
                username,
                discord_tag,
                role_label,
                1 if resolved_owner else 0,
                1 if resolved_dj else 0,
                1 if resolved_admin else 0,
                now_iso,
            ),
        )

        active_rows = conn.execute(
            """
            SELECT session_token FROM discord_user_sessions
            WHERE user_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (uid_str,),
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
                is_owner = excluded.is_owner,
                has_dj_role = excluded.has_dj_role,
                is_admin = excluded.is_admin,
                created_at = excluded.created_at
            """,
            (
                uid_str,
                new_token,
                username,
                discord_tag,
                role_label,
                1 if resolved_owner else 0,
                1 if resolved_dj else 0,
                1 if resolved_admin else 0,
                now_iso,
            ),
        )

        active_count = min(len(active_rows), MAX_SESSIONS_PER_USER)

    guild_ids_csv = ",".join(str(g).strip() for g in (user_guild_ids or []) if str(g).strip())
    if guild_ids_csv:
        try:
            with db_manager.transaction() as conn:
                conn.execute(
                    "UPDATE discord_user_sessions SET user_guild_ids = ? WHERE session_token = ?",
                    (guild_ids_csv, new_token),
                )
                conn.execute(
                    "UPDATE discord_sessions SET user_guild_ids = ? WHERE user_id = ?",
                    (guild_ids_csv, uid_str),
                )
        except Exception:
            pass

    return {
        "session_token": new_token,
        "previous_token_revoked": oldest_evicted,
        "active_sessions_count": active_count,
        "max_sessions": MAX_SESSIONS_PER_USER,
        "user": {
            "id": uid_str,
            "name": username,
            "discordTag": discord_tag,
            "roleLabel": role_label,
            "isOwner": resolved_owner,
            "hasDjRole": resolved_dj,
            "isAdmin": resolved_admin,
            "user_guild_ids": [g for g in guild_ids_csv.split(",") if g] if guild_ids_csv else [],
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
    row_keys = row.keys()
    uid_str = str(row["user_id"])
    is_owner = bool(row["is_owner"]) if "is_owner" in row_keys else (uid_str == str(settings.owner_discord_id or ""))
    if uid_str == str(settings.owner_discord_id or ""):
        is_owner = True
    is_admin = bool(row["is_admin"]) if "is_admin" in row_keys else is_owner
    if is_owner:
        is_admin = True
    has_dj = bool(row["has_dj_role"]) if "has_dj_role" in row_keys else is_admin
    raw_gids = str(row["user_guild_ids"] or "") if "user_guild_ids" in row_keys else ""
    return {
        "session_token": row["session_token"],
        "user": {
            "id": uid_str,
            "name": row["username"],
            "discordTag": row["discord_tag"],
            "roleLabel": row["role_label"],
            "isOwner": is_owner,
            "hasDjRole": has_dj,
            "isAdmin": is_admin,
            "user_guild_ids": [g.strip() for g in raw_gids.split(",") if g.strip()],
        },
    }


def get_system_metrics(actor_id: Optional[str] = None) -> Dict[str, Any]:
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
    """Membangun aplikasi FastAPI lengkap + WebSocket + Audio Stream Proxy + Static SPA."""
    if not FASTAPI_AVAILABLE:
        return None

    app_loop_ref: List[asyncio.AbstractEventLoop] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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

        clock_task = asyncio.create_task(_clock_loop())
        yield
        clock_task.cancel()
        try:
            await clock_task
        except asyncio.CancelledError:
            pass

    app = FastAPI(title="Athenaa Discord Bot & Web Dashboard API", version="1.0.0", lifespan=lifespan)

    ws_clients: Set[WebSocket] = set()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Range", "Accept-Ranges", "Content-Length", "Content-Type"],
    )

    def _build_user_voice_map() -> Dict[str, Dict[str, Any]]:
        """
        Memetakan setiap user_id Discord yang sedang berada di Voice Channel
        ke server (guild_id) dan voice_channel_id secara real-time.
        Prioritaskan server yang Voice Channel-nya juga sedang dimasuki oleh Bot.
        """
        vmap: Dict[str, Dict[str, Any]] = {}
        live_bot = getattr(app.state, "bot", None)
        if live_bot is None:
            return vmap
        try:
            for g in getattr(live_bot, "guilds", []) or []:
                gid = str(getattr(g, "id", "") or "").strip()
                gname = str(getattr(g, "name", "") or f"Server {gid}").strip()
                bot_vc = getattr(g, "voice_client", None)
                bot_ch_id = (
                    str(getattr(getattr(bot_vc, "channel", None), "id", ""))
                    if (bot_vc and getattr(bot_vc, "is_connected", lambda: False)())
                    else ""
                )
                for vc in getattr(g, "voice_channels", []) or []:
                    vc_id = str(getattr(vc, "id", "") or "")
                    vc_name = str(getattr(vc, "name", "") or "Voice Channel")
                    bot_also_here = bool(bot_ch_id and bot_ch_id == vc_id)
                    for m in getattr(vc, "members", []) or []:
                        if getattr(m, "bot", False):
                            continue
                        uid_s = str(getattr(m, "id", "") or "")
                        if not uid_s:
                            continue
                        existing = vmap.get(uid_s)
                        if not existing or (bot_also_here and not existing.get("bot_also_in_voice")):
                            vmap[uid_s] = {
                                "guild_id": gid,
                                "guild_name": gname,
                                "voice_channel_id": vc_id,
                                "voice_channel_name": vc_name,
                                "bot_also_in_voice": bot_also_here,
                            }
        except Exception:
            pass
        return vmap

    def _find_user_voice_in_guild(guild_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Mengecek apakah user_id sedang berada di Voice Channel KHUSUS pada guild_id tersebut.
        Menjamin isolasi penuh antar-server (tidak pernah bocor ke server Discord lain).
        """
        gid_s = str(guild_id or "").strip()
        uid_s = str(user_id or "").strip()
        if not gid_s or not uid_s:
            return None
        live_bot = getattr(app.state, "bot", None)
        if live_bot is None:
            return None
        try:
            for g in getattr(live_bot, "guilds", []) or []:
                if str(getattr(g, "id", "") or "").strip() != gid_s:
                    continue
                gname = str(getattr(g, "name", "") or f"Server {gid_s}").strip()
                for vc in getattr(g, "voice_channels", []) or []:
                    for m in getattr(vc, "members", []) or []:
                        if getattr(m, "bot", False):
                            continue
                        if str(getattr(m, "id", "") or "").strip() == uid_s:
                            return {
                                "guild_id": gid_s,
                                "guild_name": gname,
                                "voice_channel_id": str(getattr(vc, "id", "") or ""),
                                "voice_channel_name": str(getattr(vc, "name", "") or "Voice Channel"),
                            }
                if uid_s.isdigit() and hasattr(g, "get_member"):
                    m_obj = g.get_member(int(uid_s))
                    if m_obj and getattr(m_obj, "voice", None) and getattr(m_obj.voice, "channel", None):
                        ch = m_obj.voice.channel
                        return {
                            "guild_id": gid_s,
                            "guild_name": gname,
                            "voice_channel_id": str(ch.id),
                            "voice_channel_name": str(ch.name),
                        }
        except Exception:
            pass
        return None

    def _find_user_voice_info(user_id: str) -> Optional[Dict[str, Any]]:
        uid_s = str(user_id or "").strip()
        vmap = _build_user_voice_map()
        if uid_s and uid_s in vmap:
            return vmap[uid_s]
        live_bot = getattr(app.state, "bot", None)
        if live_bot is not None and uid_s.isdigit():
            try:
                for g in getattr(live_bot, "guilds", []) or []:
                    m = g.get_member(int(uid_s))
                    if m and getattr(m, "voice", None) and getattr(m.voice, "channel", None):
                        ch = m.voice.channel
                        return {
                            "guild_id": str(g.id),
                            "guild_name": str(g.name),
                            "voice_channel_id": str(ch.id),
                            "voice_channel_name": str(ch.name),
                            "bot_also_in_voice": True,
                        }
            except Exception:
                pass
        return None

    def _list_synchronized_guilds(
        user_id: str = "",
        user_guild_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Menyaring daftar server (guilds) di Web Player secara ketat berdasarkan irisan (Mutual Server):
        HANYA menampilkan server di mana Bot Discord bergabung DAN User yang sedang login juga bergabung!
        """
        live_bot = getattr(app.state, "bot", None)
        guild_admins_map: Dict[str, List[str]] = {}
        bot_guilds_by_id: Dict[str, Any] = {}
        uid_s = str(user_id or "").strip()
        oauth_gids_set = {str(x).strip() for x in (user_guild_ids or []) if str(x).strip()}

        if live_bot is not None:
            try:
                for g in getattr(live_bot, "guilds", []) or []:
                    gid = str(getattr(g, "id", "") or "").strip()
                    gname = str(getattr(g, "name", "") or "").strip()
                    if gid:
                        bot_guilds_by_id[gid] = g
                        queue_service.register_active_guild(gid, gname or f"Server {gid}")
                        admins: List[str] = []
                        owner_id_str = str(getattr(g, "owner_id", "") or "")
                        if owner_id_str:
                            admins.append(owner_id_str)
                        if settings.owner_discord_id:
                            admins.append(str(settings.owner_discord_id))
                        for m in getattr(g, "members", []) or []:
                            perms = getattr(m, "guild_permissions", None)
                            if getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False):
                                admins.append(str(m.id))
                        guild_admins_map[gid] = list(dict.fromkeys(admins))
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

        result_list: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            gid_r = str(d.get("guild_id") or "").strip()
            if not gid_r:
                continue

            # 1. Jika live_bot aktif dan memiliki daftar guilds, pastikan Bot benar-benar berada di server ini
            if bot_guilds_by_id and gid_r not in bot_guilds_by_id:
                continue

            # 2. Jika ada user yang login (uid_s), wajib cek apakah user tersebut join di server gid_r!
            if uid_s:
                user_in_this_server = False
                if oauth_gids_set and gid_r in oauth_gids_set:
                    user_in_this_server = True
                if not user_in_this_server and gid_r in bot_guilds_by_id:
                    g_obj = bot_guilds_by_id[gid_r]
                    if str(getattr(g_obj, "owner_id", "")) == uid_s:
                        user_in_this_server = True
                    elif uid_s.isdigit() and hasattr(g_obj, "get_member") and g_obj.get_member(int(uid_s)) is not None:
                        user_in_this_server = True
                    elif any(str(getattr(m, "id", "")) == uid_s for m in (getattr(g_obj, "members", []) or [])):
                        user_in_this_server = True
                    elif any(
                        str(getattr(m, "id", "")) == uid_s
                        for vc in (getattr(g_obj, "voice_channels", []) or [])
                        for m in (getattr(vc, "members", []) or [])
                    ):
                        user_in_this_server = True

                # Jika ada data bot_guilds_by_id atau oauth_gids_set dan user TIDAK ada di server ini, sembunyikan!
                if (bot_guilds_by_id or oauth_gids_set) and not user_in_this_server:
                    continue

            admins_for_g = list(
                guild_admins_map.get(
                    gid_r,
                    [str(settings.owner_discord_id)] if settings.owner_discord_id else [],
                )
            )
            # Izinkan user yang berada di mutual server untuk membuka & menyimpan Pengaturan Server tersebut
            if uid_s and uid_s not in admins_for_g:
                admins_for_g.append(uid_s)
            d["admin_user_ids"] = admins_for_g
            result_list.append(d)
        return result_list

    async def _broadcast_guild_state(guild_id: str) -> None:
        if not ws_clients:
            return
        vmap = _build_user_voice_map()
        st_payload = _serialize_music_state(guild_id)
        st_payload["user_voice_map"] = vmap
        payload = json.dumps(
            {
                "type": "MUSIC_STATE_UPDATE",
                "guild_id": guild_id,
                "state": st_payload,
                                "user_voice_map": vmap,
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

    def _extract_session(request: Request) -> Optional[Dict[str, Any]]:
        auth_header = request.headers.get("Authorization", "")
        bearer = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
        q_tok = request.query_params.get("session_token", "").strip()
        cookie_tok = request.cookies.get("athenaa_session_token", "").strip()
        return _get_session_from_token(bearer or q_tok or cookie_tok)

    def _verify_owner_or_admin(request: Request, guild_id: str = "") -> Dict[str, Any]:
        sess = _extract_session(request)
        if sess:
            u = sess.get("user") or {}
            uid = str(u.get("id") or "")
            if u.get("isOwner") or u.get("isAdmin") or uid == str(settings.owner_discord_id or ""):
                return sess
            live_bot = getattr(request.app.state, "bot", None)
            target_gid = guild_id or str(settings.main_guild_id or "")
            if live_bot is not None and target_gid.isdigit() and uid.isdigit():
                guild_obj = live_bot.get_guild(int(target_gid))
                if guild_obj:
                    member = guild_obj.get_member(int(uid))
                    if member and member.guild_permissions.administrator:
                        return sess
            raise HTTPException(
                status_code=403,
                detail="Akses Ditolak: Hanya Bot Owner atau Administrator Server Discord yang diizinkan mengakses fitur ini.",
            )
        # Fallback jika query is_owner=true dikirim pada mode lokal tanpa OAuth
        if request.query_params.get("is_owner") == "true" and not (settings.discord_client_id and settings.discord_client_secret):
            return {
                "session_token": "local_owner",
                "user": {
                    "id": str(settings.owner_discord_id),
                    "name": "Aetheriaaa",
                    "discordTag": "@filisim",
                    "roleLabel": "Bot Owner",
                    "isOwner": True,
                    "hasDjRole": True,
                    "isAdmin": True,
                },
            }
        raise HTTPException(status_code=401, detail="Authentication required.")

    @app.get("/health")
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "uptime_seconds": int(time.time() - START_TIME)}

    @app.websocket("/ws")
    @app.websocket("/api/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        ws_clients.add(ws)
        try:
            init_guild_id = ws.query_params.get("guild_id", "").strip() or settings.main_guild_id
            vmap_init = _build_user_voice_map()
            st_init = _serialize_music_state(init_guild_id)
            st_init["user_voice_map"] = vmap_init
            await ws.send_text(
                json.dumps(
                    {
                        "type": "MUSIC_STATE_UPDATE",
                        "guild_id": init_guild_id,
                        "state": st_init,
                                                "user_voice_map": vmap_init,
                    }
                )
            )
            while True:
                try:
                    raw_msg = await asyncio.wait_for(ws.receive_text(), timeout=25.0)
                except asyncio.TimeoutError:
                    try:
                        await ws.send_text(json.dumps({"type": "heartbeat"}))
                    except Exception:
                        break
                    continue

                if not raw_msg:
                    continue
                try:
                    data = json.loads(raw_msg)
                    msg_type = str(data.get("type") or data.get("action") or "").lower()
                    if msg_type in ("ping", "heartbeat"):
                        await ws.send_text(json.dumps({"type": "pong"}))
                except Exception:
                    pass
        except WebSocketDisconnect:
            ws_clients.discard(ws)
        except Exception:
            ws_clients.discard(ws)
        finally:
            ws_clients.discard(ws)

    # =========================================================================
    # Multi-Device Discord Authentication & OAuth2 Routes (bot.athenaa.my.id)
    # =========================================================================
    @app.get("/api/auth/session")
    async def api_auth_session(request: Request):
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
                row_keys = row.keys()
                uid_str = str(row["user_id"])
                is_owner = bool(row["is_owner"]) if "is_owner" in row_keys else (uid_str == str(settings.owner_discord_id or ""))
                is_admin = bool(row["is_admin"]) if "is_admin" in row_keys else is_owner
                has_dj = bool(row["has_dj_role"]) if "has_dj_role" in row_keys else is_admin
                return {
                    "authenticated": True,
                    "session_token": row["session_token"],
                    "user": {
                        "id": uid_str,
                        "name": row["username"],
                        "discordTag": row["discord_tag"],
                        "roleLabel": row["role_label"],
                        "isOwner": is_owner,
                        "hasDjRole": has_dj,
                        "isAdmin": is_admin,
                    },
                    "max_sessions": MAX_SESSIONS_PER_USER,
                    "oauth_configured": oauth_ready,
                }
        return {
            "authenticated": False,
            "error": "Masuk dengan akun Discord untuk mengakses panel.",
            "oauth_configured": oauth_ready,
        }

    @app.post("/api/auth/login")
    async def api_auth_login():
        return JSONResponse(
            status_code=403,
            content={
                "authenticated": False,
                "error": "Gunakan tombol Login dengan Discord OAuth2.",
            },
        )

    @app.post("/api/auth/logout")
    async def api_auth_logout(request: Request):
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
                            int(remaining["is_owner"]) if "is_owner" in remaining.keys() else 0,
                            int(remaining["has_dj_role"]) if "has_dj_role" in remaining.keys() else 0,
                            int(remaining["is_admin"]),
                            remaining["created_at"],
                        ),
                    )
        resp = JSONResponse({"ok": True})
        resp.delete_cookie("athenaa_session_token", path="/")
        return resp

    @app.get("/api/auth/discord/url")
    async def api_discord_oauth_url(request: Request):
        redirect_uri = _resolve_oauth_redirect_uri(request)
        if not settings.discord_client_id:
            return JSONResponse(
                status_code=400,
                content={
                    "oauth_configured": False,
                    "redirect_uri": redirect_uri,
                    "error": "DISCORD_CLIENT_ID belum diisi pada file .env di Pterodactyl.",
                },
            )
        params = urllib.parse.urlencode(
            {
                "client_id": settings.discord_client_id.strip(),
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "identify guilds",
                "prompt": "consent",
            }
        )
        return {
            "oauth_configured": True,
            "redirect_uri": redirect_uri,
            "url": f"https://discord.com/oauth2/authorize?{params}",
        }

    @app.get("/api/auth/discord/invite")
    @app.get("/invite")
    async def api_discord_bot_invite(request: Request, mode: str = Query("admin")):
        cid = (settings.discord_client_id or "").strip()
        if not cid and settings.discord_token and "." in settings.discord_token:
            try:
                first_part = settings.discord_token.split(".")[0]
                padded = first_part + "=" * (-len(first_part) % 4)
                decoded = base64.b64decode(padded).decode("utf-8").strip()
                if decoded.isdigit():
                    cid = decoded
            except Exception:
                pass

        if not cid:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "DISCORD_CLIENT_ID belum diisi pada file .env.",
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
        if not code or not settings.discord_client_id or not settings.discord_client_secret:
            return HTMLResponse("<h3>Parameter OAuth2 Discord tidak lengkap.</h3>", status_code=400)

        redirect_uri = _resolve_oauth_redirect_uri(request)
        try:
            data = urllib.parse.urlencode(
                {
                    "client_id": settings.discord_client_id.strip(),
                    "client_secret": settings.discord_client_secret.strip(),
                    "grant_type": "authorization_code",
                    "code": code.strip(),
                    "redirect_uri": redirect_uri,
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

            uid = str(user_data.get("id", "")).strip()
            uname = str(user_data.get("global_name") or user_data.get("username") or "DiscordUser")
            raw_username = str(user_data.get("username") or uname)
            disc = str(user_data.get("discriminator") or "0")
            utag = f"@{raw_username}" if disc == "0" else f"{raw_username}#{disc}"

            is_admin = uid == str(settings.owner_discord_id or "").strip()

            # Cek daftar server yang diikuti user (OAuth2 /users/@me/guilds) & permission Administrator
            oauth_user_guild_ids: List[str] = []
            try:
                guilds_req = urllib.request.Request(
                    "https://discord.com/api/users/@me/guilds",
                    headers={"Authorization": f"Bearer {access_token}", "User-Agent": "AthenaaBot/1.0"},
                )
                with urllib.request.urlopen(guilds_req, timeout=8.0) as gresp:
                    user_guilds = json.loads(gresp.read().decode("utf-8"))
                if isinstance(user_guilds, list):
                    for ug in user_guilds:
                        ug_id = str(ug.get("id") or "").strip()
                        if ug_id:
                            oauth_user_guild_ids.append(ug_id)
                        perms_int = int(ug.get("permissions") or 0)
                        if ug.get("owner") or (perms_int & 0x8) == 0x8 or (perms_int & 0x20) == 0x20:
                            is_admin = True
            except Exception:
                pass

            live_bot = getattr(app.state, "bot", None)
            if live_bot is not None and uid.isdigit():
                for g_obj in getattr(live_bot, "guilds", []) or []:
                    member = g_obj.get_member(int(uid))
                    if member and (member.guild_permissions.administrator or getattr(g_obj, "owner_id", 0) == member.id):
                        is_admin = True
                        break

            is_owner = is_admin
            has_dj_role = is_admin
            role_label = "Admin Server" if is_admin else "Member"

            issued = _issue_single_discord_session(
                user_id=uid,
                username=uname,
                discord_tag=utag,
                role_label=role_label,
                is_admin=is_admin,
                is_owner=is_owner,
                has_dj_role=has_dj_role,
                user_guild_ids=oauth_user_guild_ids,
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
            html_page = f"""<!doctype html>
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
            response = HTMLResponse(html_page)
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
    # Audio Stream Proxy Endpoint (Menghilangkan Blokir CORS & IP-Lock Browser)
    # =========================================================================
    @app.api_route("/api/guilds/{guild_id}/music/stream", methods=["GET", "HEAD", "OPTIONS"])
    async def api_music_stream_proxy(
        guild_id: str,
        request: Request,
        item_id: str = Query(""),
        q: str = Query(""),
    ):
        """
        Mem-proxy stream audio YouTube Music (`googlevideo.com` / radio) langsung melalui backend server
        dengan header `Access-Control-Allow-Origin: *` dan `Accept-Ranges: bytes`.
        Memastikan Web Player di browser selalu mengeluarkan suara jernih tanpa terblokir CORS!
        """
        if request.method == "OPTIONS":
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                    "Access-Control-Allow-Headers": "Range, Content-Type, Authorization",
                    "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length, Content-Type",
                },
            )

        st = queue_service.get_state(guild_id)
        target_track = None
        if item_id:
            if st.current_track and st.current_track.item_id == item_id:
                target_track = st.current_track
            else:
                target_track = next((it for it in st.queue if it.item_id == item_id), None)
        if target_track is None:
            target_track = st.current_track

        raw_stream_url = ""
        user_agent = DEFAULT_STREAM_USER_AGENT
        live_bot = getattr(request.app.state, "bot", None)

        if target_track is not None:
            if target_track.source_type == "radio" and target_track.stream_url:
                raw_stream_url = target_track.stream_url
            else:
                cand_stream = str(target_track.stream_url or "").strip()
                if cand_stream and Path(cand_stream).is_file():
                    raw_stream_url = cand_stream
                elif (
                    cand_stream.startswith(("http://", "https://"))
                    and "youtube.com/watch" not in cand_stream
                    and "youtu.be/" not in cand_stream
                    and "/api/guilds/" not in cand_stream
                ):
                    raw_stream_url = cand_stream
                    if live_bot and hasattr(live_bot, "_track_user_agents"):
                        user_agent = live_bot._track_user_agents.get(target_track.item_id, DEFAULT_STREAM_USER_AGENT)
                else:
                    extract_q = (
                        target_track.source_url
                        if target_track.source_url
                        and ("youtube.com/watch" in target_track.source_url or "youtu.be/" in target_track.source_url)
                        else f"{target_track.title} {target_track.artist}"
                    )
                    info = await asyncio.to_thread(extract_playable_stream_ytdlp, extract_q)
                    if info and info.get("stream_url"):
                        raw_stream_url = str(info["stream_url"])
                        target_track.stream_url = raw_stream_url
                        if info.get("user_agent"):
                            user_agent = str(info["user_agent"])
                            if live_bot and hasattr(live_bot, "_track_user_agents"):
                                live_bot._track_user_agents[target_track.item_id] = user_agent
                        if info.get("duration_sec") and int(info["duration_sec"]) > 0 and not target_track.duration_sec:
                            target_track.duration_sec = int(info["duration_sec"])
                        if info.get("thumbnail_url") and not target_track.thumbnail_url:
                            target_track.thumbnail_url = str(info["thumbnail_url"])
        elif q:
            info = await asyncio.to_thread(extract_playable_stream_ytdlp, q)
            if info and info.get("stream_url"):
                raw_stream_url = str(info["stream_url"])
                if info.get("user_agent"):
                    user_agent = str(info["user_agent"])

        if not raw_stream_url:
            raise HTTPException(status_code=404, detail="Stream audio belum tersedia untuk lagu ini.")

        if Path(raw_stream_url).is_file():
            ext_low = Path(raw_stream_url).suffix.lower()
            media_t = "audio/mp4" if ext_low in (".m4a", ".mp4") else "audio/mpeg" if ext_low == ".mp3" else "audio/webm"
            return FileResponse(
                path=raw_stream_url,
                media_type=media_t,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "no-cache",
                },
            )

        req_headers = {
            "User-Agent": user_agent,
            "Accept": "*/*",
            "Referer": "https://music.youtube.com/",
        }
        range_header = request.headers.get("Range") or request.headers.get("range")
        if range_header:
            req_headers["Range"] = range_header

        def _open_upstream(stream_target: str):
            upstream_req = urllib.request.Request(
                stream_target,
                headers=req_headers,
                method="HEAD" if request.method == "HEAD" else "GET",
            )
            return urllib.request.urlopen(upstream_req, timeout=12.0)

        try:
            upstream_resp = await asyncio.to_thread(_open_upstream, raw_stream_url)
        except Exception:
            # Jika URL stream googlevideo sudah kedaluwarsa, ekstrak ulang 1x
            if target_track is not None and target_track.source_type != "radio":
                from app.services.music_service import invalidate_stream_cache

                extract_q = (
                    target_track.source_url
                    if target_track.source_url
                    else f"{target_track.title} {target_track.artist}"
                )
                invalidate_stream_cache(extract_q)
                info_retry = await asyncio.to_thread(extract_playable_stream_ytdlp, extract_q)
                if info_retry and info_retry.get("stream_url"):
                    raw_stream_url = str(info_retry["stream_url"])
                    target_track.stream_url = raw_stream_url
                    try:
                        upstream_resp = await asyncio.to_thread(_open_upstream, raw_stream_url)
                    except Exception as exc2:
                        raise HTTPException(status_code=502, detail=f"Gagal memuat stream audio: {exc2}")
                else:
                    raise HTTPException(status_code=502, detail="Gagal memperbarui stream audio YouTube Music.")
            else:
                raise HTTPException(status_code=502, detail="Gagal membuka stream audio.")

        status_code = getattr(upstream_resp, "status", None) or upstream_resp.getcode() or 200
        content_type = upstream_resp.headers.get("Content-Type") or "audio/webm"
        resp_headers: Dict[str, str] = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length, Content-Type",
            "Accept-Ranges": upstream_resp.headers.get("Accept-Ranges") or "bytes",
            "Cache-Control": "no-cache",
        }
        for h_name in ("Content-Length", "Content-Range"):
            h_val = upstream_resp.headers.get(h_name)
            if h_val:
                resp_headers[h_name] = h_val

        if request.method == "HEAD":
            upstream_resp.close()
            return Response(status_code=status_code, headers=resp_headers, media_type=content_type)

        def _stream_chunks() -> Iterator[bytes]:
            try:
                while True:
                    chunk = upstream_resp.read(65536)
                    if not chunk:
                        break
                    yield chunk
            except Exception:
                pass
            finally:
                try:
                    upstream_resp.close()
                except Exception:
                    pass

        return StreamingResponse(
            _stream_chunks(),
            status_code=status_code,
            media_type=content_type,
            headers=resp_headers,
        )

    # =========================================================================
    # Guilds & Music Endpoints (25-Item Single Dropdown & Direct Playlist Play)
    # =========================================================================
    @app.get("/api/guilds")
    async def api_guilds(request: Request):
        sess = _extract_session(request)
        uid = str(sess["user"]["id"]) if sess and sess.get("user") else ""
        ugids = (sess["user"].get("user_guild_ids") if sess and sess.get("user") else None) or []
        vinfo = _find_user_voice_info(uid) if uid else None
        return {
            "guilds": _list_synchronized_guilds(user_id=uid, user_guild_ids=ugids),
            "user_voice_map": _build_user_voice_map(),
            "active_voice_guild_id": vinfo["guild_id"] if vinfo else "",
            "active_voice_channel_name": vinfo["voice_channel_name"] if vinfo else "",
        }

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
        allowed_fields = (
            "music_channel_id",
            "task_channel_id",
            "dj_role_id",
            "moodle_ics_url_encrypted",
            "reminder_days_before",
            "timezone",
            "exp_cooldown_seconds",
            "automod_badwords_enabled",
            "automod_badwords_list",
            "automod_antilink_enabled",
            "automod_antispam_enabled",
            "welcome_enabled",
            "welcome_channel_id",
            "welcome_message",
            "goodbye_enabled",
            "goodbye_message",
            "autorole_id",
            "modlog_channel_id",
            "ai_chat_enabled",
            "announce_next_track",
        )
        set_clauses = []
        params = []
        for fname in allowed_fields:
            if fname in body and body[fname] is not None:
                set_clauses.append(f"{fname} = ?")
                val = body[fname]
                if isinstance(val, bool):
                    val = 1 if val else 0
                params.append(val)
        set_clauses.append("updated_at = ?")
        params.append(now_iso)
        params.append(guild_id)

        try:
            academy_service.ensure_guild_exists(guild_id, f"Server {guild_id}")
        except Exception:
            pass
        with db_manager.transaction() as conn:
            conn.execute(
                f"UPDATE guild_settings SET {', '.join(set_clauses)} WHERE guild_id = ?",
                tuple(params),
            )
            row = conn.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
        return {"settings": dict(row) if row else {}}

    @app.get("/api/music/search")
    async def api_search_music(q: str = Query("", max_length=500)):
        cleaned_q = (q or "").strip()
        if not cleaned_q:
            return {"results": []}

        if cleaned_q:
            try:
                kind, _ = classify_music_input(cleaned_q)
                is_yt_pl = "youtube.com/playlist" in cleaned_q.lower() and "list=" in cleaned_q.lower()
                if kind in ("spotify_playlist", "spotify_album") or is_yt_pl:
                    pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, cleaned_q, 50)
                    pl_tracks = pl_data.get("tracks") or []
                    pl_name = str(pl_data.get("playlist_name") or "YouTube Music Playlist")
                    pl_thumb = str(
                        pl_data.get("thumbnail_url")
                        or (pl_tracks[0].thumbnail_url if pl_tracks else "")
                    )
                    total_dur = sum(int(t.duration_sec or 180) for t in pl_tracks)
                    dropdown_items: List[Dict[str, Any]] = [
                        {
                            "title": f"🎶 [PUTAR SEMUA PLAYLIST] {pl_name} ({len(pl_tracks)} Lagu)",
                            "artist": f"Klik Putar untuk memutar seluruh {len(pl_tracks)} lagu di Bot Discord",
                            "album": "Playlist Lengkap",
                            "duration_sec": total_dur,
                            "source_type": "spotify_playlist",
                            "source_url": cleaned_q,
                            "stream_url": "",
                            "thumbnail_url": pl_thumb,
                            "notice": "Klik Putar / +Antrean untuk memuat seluruh isi playlist",
                        }
                    ]
                    for idx_tr, tr in enumerate(pl_tracks[:49], start=1):
                        d_tr = asdict(tr)
                        d_tr["album"] = f"#{idx_tr} • {pl_name}"
                        dropdown_items.append(d_tr)
                    return {"results": dropdown_items[:50]}
            except Exception:
                pass

        if cleaned_q:
            try:
                kind_single, _ = classify_music_input(cleaned_q)
                if kind_single == "youtube" and "youtube.com/playlist" not in cleaned_q.lower():
                    direct_tr = await asyncio.to_thread(resolve_direct_youtube_video_link, cleaned_q)
                    return {"results": [asdict(direct_tr)]}
            except Exception:
                pass

        tracks = await asyncio.to_thread(search_songs_with_singer, cleaned_q, 25)
        return {"results": [asdict(t) for t in tracks[:25]]}

    @app.post("/api/music/resolve")
    async def api_resolve_music(request: Request):
        body = await request.json()
        raw_input = str(body.get("input") or body.get("query") or body.get("url") or "").strip()
        if not raw_input:
            raise HTTPException(status_code=400, detail="Masukkan judul lagu atau URL musik terlebih dahulu.")
        kind, _ = classify_music_input(raw_input)
        is_yt_pl = "youtube.com/playlist" in raw_input.lower() and "list=" in raw_input.lower()
        if kind in ("spotify_playlist", "spotify_album") or is_yt_pl:
            pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, raw_input, 50)
            tracks = pl_data.get("tracks") or []
            if not tracks:
                raise HTTPException(status_code=404, detail="Lagu dalam playlist tidak ditemukan.")
            serialized_list = [asdict(t) for t in tracks]
            return {
                "is_playlist": True,
                "playlist_name": pl_data.get("playlist_name"),
                "track": serialized_list[0],
                "tracks": serialized_list,
                "results": serialized_list,
            }
        if kind == "spotify_track":
            cand = await asyncio.to_thread(resolve_spotify_link, raw_input)
            d_cand = asdict(cand)
            return {"track": d_cand, "results": [d_cand]}
        if kind == "youtube":
            cand = await asyncio.to_thread(resolve_direct_youtube_video_link, raw_input)
            d_cand = asdict(cand)
            return {"track": d_cand, "results": [d_cand]}
        tracks = await asyncio.to_thread(search_songs_with_singer, raw_input, 5)
        if not tracks:
            raise HTTPException(status_code=404, detail="Lagu tidak ditemukan.")
        serialized_tracks = [asdict(t) for t in tracks]
        return {"track": serialized_tracks[0], "results": serialized_tracks}

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
    async def api_music_state(guild_id: str, request: Request):
        sess = _extract_session(request)
        uid = str(sess["user"]["id"]) if sess and sess.get("user") else ""
        vinfo = _find_user_voice_info(uid) if uid else None
        vc_in_this_guild = _find_user_voice_in_guild(guild_id, uid) if uid else None
        st_data = _serialize_music_state(guild_id)
        live_bot = getattr(request.app.state, "bot", None)
        if live_bot is not None and getattr(live_bot, "guilds", None):
            # Pastikan nama voice channel tidak bocor dari server lain
            g_obj = None
            for g_cand in getattr(live_bot, "guilds", []) or []:
                if str(getattr(g_cand, "id", "")) == str(guild_id):
                    g_obj = g_cand
                    break
            bot_vc = getattr(g_obj, "voice_client", None) if g_obj else None
            if bot_vc and getattr(bot_vc, "is_connected", lambda: False)() and getattr(bot_vc, "channel", None):
                st_data["voice_channel_id"] = str(bot_vc.channel.id)
                st_data["voice_channel_name"] = str(bot_vc.channel.name)
            elif vc_in_this_guild:
                st_data["voice_channel_id"] = str(vc_in_this_guild["voice_channel_id"])
                st_data["voice_channel_name"] = str(vc_in_this_guild["voice_channel_name"])
            elif not st_data.get("is_playing") and not st_data.get("is_paused"):
                st_data["voice_channel_id"] = ""
                st_data["voice_channel_name"] = "Belum Terhubung"
        st_data["user_voice_map"] = _build_user_voice_map()
        st_data["active_voice_guild_id"] = vinfo["guild_id"] if vinfo else ""
        st_data["user_in_this_guild_voice"] = bool(vc_in_this_guild)
        return st_data

    @app.post("/api/guilds/{guild_id}/music/play")
    async def api_music_play(
        guild_id: str,
        request: Request,
        body: PlayMusicRequest,
        _rl: None = Depends(rate_limit_dependency),
    ):
        sess = _extract_session(request)
        requester_id = sess["user"]["id"] if sess else str(body.requester_id or settings.owner_discord_id or "guest")
        requester_name = sess["user"]["name"] if sess else str(body.requester_name or "Discord Member")
        is_admin = True
        is_owner = True

        # STRICT PER-GUILD VOICE ISOLATION (Referensi ItzSudhan/Discord-MusicBot v5.1):
        # User WAJIB berada di Voice Channel pada server (guild_id) yang sedang dibuka ini!
        # Jika user tidak join voice di server ini (atau sedang join voice di server LAIN),
        # TOLAK (400) dan JANGAN PERNAH memutar/nyasar ke server Discord lain!
        live_bot = getattr(request.app.state, "bot", None)
        if live_bot is not None and getattr(live_bot, "guilds", None):
            vc_in_guild = _find_user_voice_in_guild(guild_id, requester_id)
            if vc_in_guild is None:
                other_vinfo = _find_user_voice_info(requester_id)
                if other_vinfo and str(other_vinfo.get("guild_id")) != str(guild_id):
                    audit_log(
                        "music_play_denied_cross_guild",
                        requester_id,
                        guild_id,
                        f"User in voice on another guild ({other_vinfo.get('guild_name')}), blocked on {guild_id}",
                        False,
                    )
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": (
                                f"Kamu sedang tidak berada di Voice Channel pada server ini! "
                                f"Saat ini kamu terdeteksi di Voice Channel '{other_vinfo.get('voice_channel_name')}' "
                                f"pada server '{other_vinfo.get('guild_name')}'. "
                                f"Silakan masuk ke Voice Channel di server ini terlebih dahulu."
                            ),
                            "active_voice_guild_id": str(other_vinfo.get("guild_id") or ""),
                        },
                    )
                audit_log("music_play_denied", requester_id, guild_id, "User not in Voice Channel in this guild", False)
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Kamu wajib join ke Voice Channel di server Discord ini terlebih dahulu sebelum memutar musik lewat Web Player!"
                    },
                )
            st_vc = queue_service.get_state(guild_id)
            st_vc.voice_channel_id = str(vc_in_guild["voice_channel_id"])
            st_vc.voice_channel_name = str(vc_in_guild["voice_channel_name"])

        audit_log("music_play", requester_id, guild_id, f"title={body.title}, artist={body.artist}, play_now={body.play_now}")

        try:
            raw_url = str(body.source_url or "").strip()
            input_kind = ""
            try:
                input_kind, _ = classify_music_input(raw_url)
            except Exception:
                input_kind = ""
            is_yt_pl = "youtube.com/playlist" in raw_url.lower() and "list=" in raw_url.lower()

            if (
                body.source_type in ("spotify_playlist", "spotify_album", "youtube_playlist")
                or input_kind in ("spotify_playlist", "spotify_album")
                or is_yt_pl
            ):
                pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, raw_url, 50)
                pl_tracks = pl_data.get("tracks") or []
                if not pl_tracks:
                    return JSONResponse(status_code=404, content={"error": "Playlist kosong atau tidak terbaca."})

                first_item = None
                started_any = False
                for idx, tr in enumerate(pl_tracks):
                    item_added, started = queue_service.add_track(
                        guild_id=guild_id,
                        title=tr.title,
                        artist=tr.artist,
                        album=tr.album or str(pl_data.get("playlist_name") or "YouTube Music Playlist"),
                        duration_sec=int(tr.duration_sec or 180),
                        source_type="spotify_matched",
                        source_url=tr.source_url,
                        stream_url="",
                        thumbnail_url=tr.thumbnail_url,
                        requester_id=requester_id,
                        requester_name=requester_name,
                        play_now=(bool(body.play_now) and idx == 0),
                        user_roles=body.user_roles or [],
                        is_admin=is_admin,
                        is_owner=is_owner,
                        dj_role_id=settings.dj_role_id,
                    )
                    if idx == 0:
                        first_item = item_added
                    if started:
                        started_any = True

                if live_bot is not None and hasattr(live_bot, "_schedule_coro") and hasattr(live_bot, "start_or_sync_voice_playback"):
                    live_bot._schedule_coro(live_bot.start_or_sync_voice_playback(guild_id, requester_id))

                return {
                    "item": _serialize_track_for_web(first_item) if first_item else {},
                    "playlist_tracks_added": len(pl_tracks),
                    "started_immediately": started_any,
                    "redirect_guild_id": guild_id,
                    "state": _serialize_music_state(guild_id),
                }

            final_title = body.title
            final_artist = body.artist or "YouTube Music Artist"
            final_album = body.album or "YouTube Music"
            final_dur = int(body.duration_sec or 180)
            final_source_type = body.source_type or "spotify_matched"
            final_source_url = raw_url
            final_stream_url = body.stream_url or ""
            final_thumb = body.thumbnail_url or ""

            if input_kind == "youtube" or (
                YOUTUBE_URL_RE.match(raw_url) and "results?search_query=" not in raw_url
            ):
                # Aturan Direct Link YouTube: putar 1 lagu presisi sesuai link YouTube yang diberikan user
                direct_cand = await asyncio.to_thread(resolve_direct_youtube_video_link, raw_url)
                final_title = direct_cand.title or final_title
                final_artist = direct_cand.artist or final_artist
                final_album = direct_cand.album or "YouTube Direct Link"
                final_dur = int(direct_cand.duration_sec or final_dur)
                final_source_type = "youtube"
                final_source_url = direct_cand.source_url or raw_url
                final_thumb = direct_cand.thumbnail_url or final_thumb
            elif final_source_type != "radio":
                search_q = (
                    f"{final_title} {final_artist}".strip()
                    if final_artist.lower() not in ("unknown", "youtube music artist", "spotify artist", "pencarian langsung")
                    else final_title
                )
                resolved_list = await asyncio.to_thread(search_songs_with_singer, search_q, 3)
                if resolved_list:
                    best = resolved_list[0]
                    final_title = best.title
                    final_artist = best.artist
                    final_album = best.album or final_album
                    final_dur = int(best.duration_sec or final_dur)
                    final_source_url = best.source_url or final_source_url
                    final_thumb = best.thumbnail_url or final_thumb

            item, started = queue_service.add_track(
                guild_id=guild_id,
                title=final_title,
                artist=final_artist,
                album=final_album,
                duration_sec=final_dur,
                source_type=final_source_type,
                source_url=final_source_url,
                stream_url=final_stream_url,
                thumbnail_url=final_thumb,
                requester_id=requester_id,
                requester_name=requester_name,
                play_now=bool(body.play_now),
                user_roles=body.user_roles or [],
                is_admin=is_admin,
                is_owner=is_owner,
                dj_role_id=settings.dj_role_id,
            )
            if live_bot is not None and hasattr(live_bot, "_schedule_coro") and hasattr(live_bot, "start_or_sync_voice_playback"):
                live_bot._schedule_coro(live_bot.start_or_sync_voice_playback(guild_id, requester_id))

            return {
                "item": _serialize_track_for_web(item),
                "started_immediately": started,
                "redirect_guild_id": guild_id,
                "state": _serialize_music_state(guild_id),
            }
        except PermissionError as exc:
            audit_log("music_play_denied", requester_id, guild_id, str(exc), False)
            return JSONResponse(status_code=403, content={"error": str(exc)})

    @app.post("/api/guilds/{guild_id}/music/control")
    async def api_music_control(
        guild_id: str,
        request: Request,
        body: ControlMusicRequest,
        _rl: None = Depends(rate_limit_dependency),
    ):
        sess = _extract_session(request)
        actor_id = sess["user"]["id"] if sess else str(body.actor_id or settings.owner_discord_id or "web-remote")
        is_owner = True
        is_admin = True

        live_bot = getattr(request.app.state, "bot", None)
        if live_bot is not None and getattr(live_bot, "guilds", None) and body.action in ("play_item", "resume", "skip", "pause", "stop"):
            vc_in_guild = _find_user_voice_in_guild(guild_id, actor_id)
            if vc_in_guild is None:
                other_vinfo = _find_user_voice_info(actor_id)
                if other_vinfo and str(other_vinfo.get("guild_id")) != str(guild_id):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": (
                                f"Kamu sedang tidak berada di Voice Channel pada server ini! "
                                f"Saat ini kamu berada di Voice '{other_vinfo.get('voice_channel_name')}' "
                                f"pada server '{other_vinfo.get('guild_name')}'."
                            )
                        },
                    )
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Kamu wajib join ke Voice Channel di server Discord ini terlebih dahulu untuk mengontrol pemutaran musik!"
                    },
                )
            st_vc = queue_service.get_state(guild_id)
            st_vc.voice_channel_id = str(vc_in_guild["voice_channel_id"])
            st_vc.voice_channel_name = str(vc_in_guild["voice_channel_name"])

        audit_log("music_control", actor_id, guild_id, f"action={body.action}, item_id={body.item_id}")

        try:
            if body.action == "play_item":
                queue_service.play_queue_item(
                    guild_id=guild_id,
                    item_id=body.item_id or "",
                    actor_id=actor_id,
                    user_roles=body.user_roles or [],
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=settings.dj_role_id,
                )
            elif body.action == "remove_item":
                queue_service.remove_item(
                    guild_id=guild_id,
                    item_id=body.item_id or "",
                    actor_id=actor_id,
                    user_roles=body.user_roles or [],
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=settings.dj_role_id,
                )
            elif body.action == "move_to_top":
                queue_service.move_to_top(
                    guild_id=guild_id,
                    item_id=body.item_id or "",
                    actor_id=actor_id,
                    user_roles=body.user_roles or [],
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=settings.dj_role_id,
                )
            else:
                queue_service.control_session(
                    guild_id=guild_id,
                    action=body.action,
                    actor_id=actor_id,
                    user_roles=body.user_roles or [],
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=settings.dj_role_id,
                    value=body.value,
                )
            return {"ok": True, "redirect_guild_id": guild_id, "state": _serialize_music_state(guild_id)}
        except (PermissionError, KeyError, ValueError) as exc:
            audit_log("music_control_denied", actor_id, guild_id, str(exc), False)
            return JSONResponse(status_code=403, content={"error": str(exc)})

    # =========================================================================
    # Library, Favorites & Playlists Endpoints
    # =========================================================================
    @app.get("/api/guilds/{guild_id}/library")
    async def api_guild_library(guild_id: str, request: Request):
        sess = _extract_session(request)
        user_id = sess["user"]["id"] if sess else settings.owner_discord_id
        with db_manager.transaction() as conn:
            favs = conn.execute(
                "SELECT * FROM favorites WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            pls = conn.execute(
                "SELECT * FROM playlists WHERE guild_id = ? ORDER BY created_at DESC",
                (guild_id,),
            ).fetchall()
            playlists_result = []
            for p in pls:
                items = conn.execute(
                    "SELECT * FROM playlist_items WHERE playlist_id = ? ORDER BY position ASC",
                    (p["playlist_id"],),
                ).fetchall()
                d = dict(p)
                d["items"] = [dict(i) for i in items]
                playlists_result.append(d)
        return {
            "favorites": [dict(f) for f in favs],
            "playlists": playlists_result,
        }

    @app.get("/api/favorites")
    async def api_get_favorites(user_id: str = Query("")):
        uid = user_id or settings.owner_discord_id
        with db_manager.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM favorites WHERE user_id = ? ORDER BY created_at DESC",
                (uid,),
            ).fetchall()
        return {"favorites": [dict(r) for r in rows]}

    @app.post("/api/favorites")
    @app.post("/api/guilds/{guild_id}/favorites")
    async def api_add_favorite(request: Request, guild_id: str = ""):
        body = await request.json()
        sess = _extract_session(request)
        user_id = sess["user"]["id"] if sess else str(body.get("user_id") or settings.owner_discord_id)
        fav_id = f"fav-{uuid.uuid4().hex[:10]}"
        with db_manager.transaction() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO favorites (
                    favorite_id, user_id, title, artist, album, duration_sec,
                    source_type, source_url, thumbnail_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fav_id,
                    user_id,
                    str(body.get("title", "")),
                    str(body.get("artist", "")),
                    str(body.get("album", "")),
                    int(body.get("duration_sec", 0)),
                    str(body.get("source_type", "youtube")),
                    str(body.get("source_url", "")),
                    str(body.get("thumbnail_url", "")),
                    _utc_now(),
                ),
            )
        return {"ok": True, "favorite_id": fav_id}

    @app.delete("/api/favorites/{favorite_id}")
    async def api_delete_favorite(favorite_id: str):
        with db_manager.transaction() as conn:
            conn.execute("DELETE FROM favorites WHERE favorite_id = ?", (favorite_id,))
        return {"ok": True}

    @app.get("/api/guilds/{guild_id}/playlists")
    async def api_get_playlists(guild_id: str):
        with db_manager.transaction() as conn:
            pls = conn.execute("SELECT * FROM playlists WHERE guild_id = ? ORDER BY created_at DESC", (guild_id,)).fetchall()
            result = []
            for p in pls:
                items = conn.execute(
                    "SELECT * FROM playlist_items WHERE playlist_id = ? ORDER BY position ASC",
                    (p["playlist_id"],),
                ).fetchall()
                d = dict(p)
                d["items"] = [dict(i) for i in items]
                result.append(d)
        return {"playlists": result}

    @app.post("/api/guilds/{guild_id}/playlists/save-queue")
    async def api_save_queue_playlist(guild_id: str, request: Request):
        body = await request.json()
        sess = _extract_session(request)
        owner_id = sess["user"]["id"] if sess else str(body.get("owner_user_id") or settings.owner_discord_id)
        owner_name = sess["user"]["name"] if sess else str(body.get("owner_username") or "Aetheriaaa")
        st = queue_service.get_state(guild_id)
        tracks = []
        if st.current_track:
            tracks.append(st.current_track)
        tracks.extend(st.queue)
        if not tracks:
            return JSONResponse(status_code=400, content={"error": "Tidak ada lagu di antrean untuk disimpan."})

        playlist_id = f"pl-{uuid.uuid4().hex[:8]}"
        now_iso = _utc_now()
        with db_manager.transaction() as conn:
            conn.execute(
                """
                INSERT INTO playlists (playlist_id, guild_id, owner_user_id, owner_username, name, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    playlist_id,
                    guild_id,
                    owner_id,
                    owner_name,
                    str(body.get("name", "Playlist Server")),
                    str(body.get("description", "")),
                    now_iso,
                ),
            )
            for idx, tr in enumerate(tracks, start=1):
                conn.execute(
                    """
                    INSERT INTO playlist_items (
                        id, playlist_id, position, title, artist, album,
                        duration_sec, source_type, source_url, thumbnail_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"pli-{uuid.uuid4().hex[:10]}",
                        playlist_id,
                        idx,
                        tr.title,
                        tr.artist,
                        tr.album,
                        tr.duration_sec,
                        tr.source_type,
                        tr.source_url,
                        tr.thumbnail_url,
                    ),
                )
        return {"ok": True, "playlist_id": playlist_id}

    @app.post("/api/guilds/{guild_id}/playlists/import-spotify")
    async def api_import_spotify_playlist(
        guild_id: str,
        request: Request,
        _rl: None = Depends(rate_limit_dependency),
    ):
        body = await request.json()
        sess = _extract_session(request)
        owner_id = sess["user"]["id"] if sess else str(body.get("owner_user_id") or settings.owner_discord_id)
        owner_name = sess["user"]["name"] if sess else str(body.get("owner_username") or "Aetheriaaa")
        spotify_url = str(body.get("spotify_url") or body.get("url") or "").strip()
        custom_name = str(body.get("name") or "").strip()
        play_immediately = bool(body.get("play_immediately") or body.get("queue_now") or True)

        if not spotify_url:
            return JSONResponse(status_code=400, content={"error": "Masukkan link Playlist atau Album Spotify terlebih dahulu."})

        audit_log("spotify_import", owner_id, guild_id, f"url={spotify_url}")

        try:
            pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, spotify_url, 50)
        except Exception as exc:
            audit_log("spotify_import_failed", owner_id, guild_id, str(exc), False)
            return JSONResponse(status_code=400, content={"error": f"Gagal membaca playlist Spotify: {exc}"})

        tracks = pl_data.get("tracks") or []
        if not tracks:
            return JSONResponse(status_code=404, content={"error": "Tidak ditemukan lagu di dalam playlist Spotify tersebut."})

        playlist_name = custom_name or str(pl_data.get("playlist_name") or "Spotify Playlist")
        playlist_id = f"pl-{uuid.uuid4().hex[:8]}"
        now_iso = _utc_now()

        with db_manager.transaction() as conn:
            conn.execute(
                """
                INSERT INTO playlists (playlist_id, guild_id, owner_user_id, owner_username, name, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    playlist_id,
                    guild_id,
                    owner_id,
                    owner_name,
                    playlist_name,
                    f"Diimpor dari Spotify ({spotify_url})",
                    now_iso,
                ),
            )
            for idx, tr in enumerate(tracks, start=1):
                conn.execute(
                    """
                    INSERT INTO playlist_items (
                        id, playlist_id, position, title, artist, album,
                        duration_sec, source_type, source_url, thumbnail_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"pli-{uuid.uuid4().hex[:10]}",
                        playlist_id,
                        idx,
                        tr.title,
                        tr.artist,
                        tr.album,
                        tr.duration_sec,
                        tr.source_type,
                        tr.source_url,
                        tr.thumbnail_url,
                    ),
                )

        if play_immediately:
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
            "playlist_id": playlist_id,
            "name": playlist_name,
            "playlist_name": playlist_name,
            "tracks_count": len(tracks),
            "played": play_immediately,
            "state": _serialize_music_state(guild_id),
        }

    @app.post("/api/guilds/{guild_id}/playlists/{playlist_id}/play")
    async def api_play_playlist(guild_id: str, playlist_id: str, request: Request):
        sess = _extract_session(request)
        req_id = sess["user"]["id"] if sess else settings.owner_discord_id
        req_name = sess["user"]["name"] if sess else "Aetheriaaa"
        with db_manager.transaction() as conn:
            items = conn.execute(
                "SELECT * FROM playlist_items WHERE playlist_id = ? ORDER BY position ASC",
                (playlist_id,),
            ).fetchall()
        for it in items:
            queue_service.add_track(
                guild_id=guild_id,
                title=str(it["title"]),
                artist=str(it["artist"]),
                album=str(it["album"] or ""),
                duration_sec=int(it["duration_sec"] or 180),
                source_type=str(it["source_type"] or "spotify_matched"),
                source_url=str(it["source_url"] or ""),
                stream_url="",
                thumbnail_url=str(it["thumbnail_url"] or ""),
                requester_id=req_id,
                requester_name=req_name,
                play_now=False,
            )
        return {"ok": True, "state": _serialize_music_state(guild_id)}

    @app.delete("/api/guilds/{guild_id}/playlists/{playlist_id}")
    async def api_delete_playlist(guild_id: str, playlist_id: str):
        with db_manager.transaction() as conn:
            conn.execute("DELETE FROM playlists WHERE playlist_id = ? AND guild_id = ?", (playlist_id, guild_id))
        return {"ok": True}

    # =========================================================================
    # Academy Tasks, Modules & RPG Endpoints
    # =========================================================================
    @app.get("/api/guilds/{guild_id}/tasks")
    async def api_get_tasks(guild_id: str):
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
    async def api_create_task(
        guild_id: str,
        request: Request,
        body: TaskCreateRequest,
        _rl: None = Depends(rate_limit_dependency),
    ):
        sess = _extract_session(request)
        creator = sess["user"]["name"] if sess else body.created_by

        audit_log("task_create", sess["user"]["id"] if sess else creator, guild_id, f"title={body.title}")

        task = academy_service.create_task(
            guild_id=guild_id,
            course_name=body.course_name,
            title=body.title,
            deadline_iso=body.deadline_iso,
            created_by=creator,
            description=body.description,
            source_url=body.source_url,
        )
        return {"task": asdict(task)}

    @app.patch("/api/guilds/{guild_id}/tasks/{task_id}")
    async def api_patch_task(
        guild_id: str,
        task_id: str,
        request: Request,
        body: TaskPatchRequest,
        _rl: None = Depends(rate_limit_dependency),
    ):
        sess = _extract_session(request)
        actor_name = sess["user"]["name"] if sess else body.actor_name

        audit_log("task_patch", sess["user"]["id"] if sess else actor_name, guild_id, f"task_id={task_id}, completed={body.is_completed}")

        if body.is_completed is not None:
            academy_service.set_task_completion(
                guild_id=guild_id,
                task_id=task_id,
                completed=body.is_completed,
                actor_name=actor_name,
            )
        return {"ok": True}

    @app.post("/api/tasks/{task_id}/toggle")
    async def api_toggle_task(
        task_id: str,
        request: Request,
        _rl: None = Depends(rate_limit_dependency),
    ):
        sess = _extract_session(request)
        actor_name = sess["user"]["name"] if sess else "Aetheriaaa"

        audit_log("task_toggle", sess["user"]["id"] if sess else actor_name, "", f"task_id={task_id}")

        updated = academy_service.toggle_task(task_id=task_id, actor_name=actor_name)
        if not updated:
            raise HTTPException(status_code=404, detail="Tugas tidak ditemukan.")
        return {"ok": True, "task": asdict(updated)}

    @app.delete("/api/guilds/{guild_id}/tasks/{task_id}")
    async def api_delete_guild_task(
        guild_id: str,
        task_id: str,
        request: Request,
        _rl: None = Depends(rate_limit_dependency),
    ):
        sess = _extract_session(request)
        audit_log("task_delete", sess["user"]["id"] if sess else "user", guild_id, f"task_id={task_id}")
        academy_service.delete_task(guild_id, task_id)
        return {"ok": True}

    @app.delete("/api/tasks/{task_id}")
    async def api_delete_task_by_id(
        task_id: str,
        request: Request,
        _rl: None = Depends(rate_limit_dependency),
    ):
        sess = _extract_session(request)
        audit_log("task_delete", sess["user"]["id"] if sess else "user", "", f"task_id={task_id}")
        academy_service.delete_task("", task_id)
        return {"ok": True}

    @app.post("/api/guilds/{guild_id}/tasks/sync-ics")
    @app.post("/api/guilds/{guild_id}/tasks/sync-moodle")
    async def api_sync_moodle(guild_id: str, request: Request):
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
    async def api_upload_module(
        guild_id: str,
        request: Request,
        body: ModuleUploadRequest,
        _rl: None = Depends(rate_limit_dependency),
    ):
        sess = _extract_session(request)
        uploader = sess["user"]["name"] if sess else "Aetheriaaa"

        audit_log("module_upload", sess["user"]["id"] if sess else uploader, guild_id, f"filename={body.filename}, size={body.size_bytes}")

        ext = Path(body.filename).suffix.lower()
        sample_magic = (
            _build_valid_pdf_bytes(body.filename, uploader, "new")
            if ext == ".pdf"
            else b"PK\x03\x04 Athenaa DOCX"
            if ext == ".docx"
            else b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 Athenaa DOC"
            if ext == ".doc"
            else b"UNKNOWN"
        )
        ok, err_msg, stored_name = sanitize_and_validate_attachment(body.filename, sample_magic, max_mb=15)
        if not ok:
            audit_log("module_upload_failed", sess["user"]["id"] if sess else uploader, guild_id, err_msg, False)
            return JSONResponse(status_code=400, content={"error": err_msg})

        mime_type = (
            "application/pdf"
            if ext == ".pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if ext == ".docx"
            else "application/msword"
        )

        content_b64 = str(body.content_base64 or "")
        if "," in content_b64:
            content_b64 = content_b64.split(",", 1)[1]
        try:
            file_bytes = base64.b64decode(content_b64) if content_b64 else sample_magic
        except Exception:
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

        final_size = len(file_bytes) if file_bytes else body.size_bytes

        att_id = f"att-{uuid.uuid4().hex[:10]}"
        now_iso = _utc_now()
        with db_manager.transaction() as conn:
            task_id = body.task_id
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
                (att_id, task_id, guild_id, body.filename, stored_name, mime_type, final_size, uploader, now_iso),
            )
        return {
            "ok": True,
            "attachment": {
                "attachment_id": att_id,
                "task_id": task_id,
                "guild_id": guild_id,
                "original_filename": body.filename,
                "stored_filename": stored_name,
                "mime_type": mime_type,
                "size_bytes": final_size,
                "uploaded_by": uploader,
                "created_at": now_iso,
            },
        }

    @app.get("/api/modules/{attachment_id}/download")
    async def api_download_module(attachment_id: str, request: Request):
        with db_manager.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM task_attachments WHERE attachment_id = ?",
                (attachment_id,),
            ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Modul tidak ditemukan.")

        row_data = dict(row)
        stored_name = Path(str(row_data.get("stored_filename") or f"{attachment_id}.pdf")).name
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
        return {
            "leaderboard": leveling_service.get_leaderboard(guild_id, limit=15),
            "afk_list": leveling_service.list_afk(guild_id),
        }

    @app.post("/api/guilds/{guild_id}/rpg/activity")
    async def api_rpg_activity(
        guild_id: str,
        request: Request,
        _rl: None = Depends(rate_limit_dependency),
    ):
        sess = _extract_session(request)
        if not sess or not (sess["user"].get("isOwner") or sess["user"].get("isAdmin")):
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Akses Ditolak: Fitur Uji Aktivitas & Simulasi EXP hanya dapat diakses oleh Bot Owner atau Administrator Server Discord."
                },
            )

        body = await request.json()
        uid = sess["user"]["id"]
        uname = (sess["user"]["discordTag"].lstrip("@") if sess else "filisim") or "filisim"
        dname = sess["user"]["name"]
        activity_type = str(body.get("activity_type", "chat")).strip().lower()
        msg = str(body.get("message_content", "Aktivitas di server"))
        bypass = bool(body.get("bypass_cooldown", False))

        audit_log("rpg_activity", uid, guild_id, f"type={activity_type}, bypass={bypass}")

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
    async def api_set_afk(
        guild_id: str,
        request: Request,
        _rl: None = Depends(rate_limit_dependency),
    ):
        body = await request.json()
        sess = _extract_session(request)
        uid = sess["user"]["id"] if sess else str(body.get("user_id") or settings.owner_discord_id)
        uname = sess["user"]["name"] if sess else str(body.get("username") or "Aetheriaaa")
        reason = str(body.get("reason", "Sedang AFK"))[:200]

        audit_log("afk_set", uid, guild_id, f"reason={reason}")

        leveling_service.set_afk(
            guild_id=guild_id,
            user_id=uid,
            username=uname,
            reason=reason,
        )
        return {"ok": True}

    @app.delete("/api/guilds/{guild_id}/afk/{user_id}")
    async def api_clear_afk(
        guild_id: str,
        user_id: str,
        request: Request,
        _rl: None = Depends(rate_limit_dependency),
    ):
        sess = _extract_session(request)
        if sess and user_id != sess["user"]["id"] and not (sess["user"].get("isAdmin") or sess["user"].get("isOwner")):
            raise HTTPException(status_code=403, detail="Tidak dapat menghapus AFK pengguna lain.")

        audit_log("afk_clear", sess["user"]["id"] if sess else user_id, guild_id, f"target={user_id}")

        leveling_service.clear_afk(guild_id, user_id)
        return {"ok": True}

    # =========================================================================
    # Super-Admin & Python Codebase Endpoints
    # =========================================================================
    @app.get("/api/admin/metrics")
    async def api_admin_metrics(request: Request, guild_id: str = Query("")):
        _verify_owner_or_admin(request, guild_id)
        return get_system_metrics(settings.owner_discord_id)

    @app.post("/api/admin/backup")
    async def api_admin_backup(request: Request, guild_id: str = Query("")):
        sess = _verify_owner_or_admin(request, guild_id)
        audit_log("admin_backup", sess["user"]["id"], guild_id)
        return backup_service.create_consistent_backup(encrypt=True)

    @app.post("/api/admin/yt-dlp")
    async def api_admin_ytdlp(request: Request, guild_id: str = Query("")):
        sess = _verify_owner_or_admin(request, guild_id)
        audit_log("admin_ytdlp", sess["user"]["id"], guild_id)
        try:
            body = await request.json()
        except Exception:
            body = {}
        return BackupService.check_and_update_ytdlp(perform_update=bool(body.get("perform_update", False)))

    @app.post("/api/admin/run-tests")
    async def api_admin_tests(request: Request, guild_id: str = Query("")):
        sess = _verify_owner_or_admin(request, guild_id)
        audit_log("admin_run_tests", sess["user"]["id"], guild_id)
        return run_test_suite()

    @app.get("/api/python-codebase")
    async def api_python_codebase(request: Request, file: str = Query("app/main.py")):
        raise HTTPException(status_code=404, detail="Fitur kode sumber bot disembunyikan.")

    @app.get("/api/python-codebase/download-zip")
    async def api_download_zip(request: Request):
        raise HTTPException(status_code=404, detail="Fitur unduhan kode bot disembunyikan.")

    # =========================================================================
    # Serve Pre-Built React Web UI (app/web/static) on Port 10031
    # =========================================================================
    if (STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        no_cache_headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        candidate = (STATIC_DIR / full_path).resolve()
        if (
            full_path
            and str(candidate).startswith(str(STATIC_DIR.resolve()))
            and candidate.is_file()
        ):
            return FileResponse(str(candidate), headers=no_cache_headers)
        index_html = STATIC_DIR / "index.html"
        if index_html.exists():
            raw_html = index_html.read_text(encoding="utf-8", errors="ignore")
            raw_html = raw_html.replace("/assets/index-t6EOnP72.js", "/assets/athenaa-ui-v51.js?v=20261116b")
            if "</body>" in raw_html:
                patched_html = raw_html.replace("</body>", f"{UI_CUSTOMIZATION_INJECTION}\n</body>")
            else:
                patched_html = raw_html + UI_CUSTOMIZATION_INJECTION
            return HTMLResponse(patched_html, headers=no_cache_headers)
        return JSONResponse({"status": "Athenaa API Running", "web_ui": "Jalankan npm run build untuk menyertakan static UI"})

    return app