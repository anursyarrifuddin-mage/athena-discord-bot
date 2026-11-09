"""
Implementasi Bot Discord Athenaa menggunakan discord.py (app_commands / Slash Commands).
Fitur Utama:
- Modern Rich Embeds (UI Embed Discord modern dengan progress bar visual, badge sumber, & warna dinamis).
- Eksekusi audio nyata di Voice Channel menggunakan FFmpegOpusAudio + yt-dlp (YouTube, Spotify, & Radio).
- Host Lock System & Otomatisasi Transfer Host saat Session Host keluar dari Voice Channel.
- Sistem Pengingat Tugas & Waskita (/tugas, /tugas_list, /tugas_add, /tugas_done, /tugas_hapus, /sync_waskita)
  beserta pengiriman file modul lampiran (.pdf/.doc/.docx) langsung ke Discord.
- Sistem Leveling & Leaderboard (Tanpa kata RPG) dari aktivitas:
  1. Chat di Server Discord
  2. Join Voice Channel (+20 EXP)
  3. Speak / Unmuted di Voice Channel (+15 EXP)
  4. Listening di Voice Channel (+10 EXP)
  5. Streaming / Share Screen / Cam di Voice Channel (+25 EXP)
  6. Minigames & Produktivitas Mahasiswa (+15 s/d +30 EXP)
- Addon Utilitas Mahasiswa (/pomodoro, /ipk, /kelompok, /sync_moodle) & Minigames Interaktif (/kuis, /mathbattle, /suit, /8ball, /dadu).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import shutil
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

try:
    import discord
    from discord import app_commands
    from discord.ext import commands
    DISCORD_PY_AVAILABLE = True
except ImportError:
    DISCORD_PY_AVAILABLE = False

    class _DummyDecorator:
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            def _wrap(fn: Any) -> Any:
                return fn
            return _wrap

    class _DummyTree:
        def command(self, *args: Any, **kwargs: Any) -> Any:
            def _wrap(fn: Any) -> Any:
                fn.autocomplete = lambda *_a, **_kw: (lambda f: f)
                return fn
            return _wrap

        def clear_commands(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def sync(self, *args: Any, **kwargs: Any) -> list[Any]:
            return []

    class _DummyBotBase:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.tree = _DummyTree()
            self.guilds: list[Any] = []
            self.voice_clients: list[Any] = []
            self.user = None

        def get_guild(self, _gid: int) -> Any:
            return None

        def get_channel(self, _cid: int) -> Any:
            return None

        def is_closed(self) -> bool:
            return False

    class _DummyUI:
        class View:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.children: List[Any] = []
                for attr_name in dir(self.__class__):
                    attr = getattr(self.__class__, attr_name, None)
                    if callable(attr) and getattr(attr, "_is_ui_button", False):
                        self.children.append(attr)

            def add_item(self, item: Any, *args: Any, **kwargs: Any) -> None:
                self.children.append(item)

        class Button:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.kwargs = kwargs

        @staticmethod
        def button(*args: Any, **kwargs: Any) -> Any:
            def _wrap(fn: Any) -> Any:
                fn._is_ui_button = True
                fn._button_kwargs = kwargs
                return fn
            return _wrap


    class _DummyEmbed:
        def __init__(self, **kw: Any) -> None:
            self.title = kw.get("title", "")
            self.description = kw.get("description", "")
            self.color = kw.get("color", 0)
            self.fields: List[Any] = []

        def set_author(self, **kw: Any) -> None:
            self.author = kw

        def set_thumbnail(self, **kw: Any) -> None:
            self.thumbnail = kw

        def set_footer(self, **kw: Any) -> None:
            self.footer = kw

        def add_field(self, **kw: Any) -> None:
            self.fields.append(type("EmbedField", (), kw)())

    class _DummyDiscord:
        Intents = type("Intents", (), {"default": staticmethod(lambda: type("I", (), {})())})
        Embed = _DummyEmbed
        Color = staticmethod(lambda c=0: c)
        ButtonStyle = type("ButtonStyle", (), {"primary": 1, "secondary": 2, "success": 3, "danger": 4, "link": 5})

        Interaction = Any
        Member = Any
        VoiceState = Any
        Message = Any
        Attachment = Any
        File = Any
        Object = staticmethod(lambda id=0: id)
        Activity = staticmethod(lambda **kw: kw)
        ActivityType = type("ActivityType", (), {"listening": 2})
        FFmpegOpusAudio = Any
        PCMVolumeTransformer = Any
        FFmpegPCMAudio = Any
        ui = _DummyUI

    class _DummyAppCommands:
        command = _DummyDecorator()
        describe = _DummyDecorator()
        choices = _DummyDecorator()
        Choice = staticmethod(lambda name="", value="": (name, value))

    class _DummyCommands:
        Bot = _DummyBotBase

    discord = _DummyDiscord()  # type: ignore
    app_commands = _DummyAppCommands()  # type: ignore
    commands = _DummyCommands()  # type: ignore

from app.config import settings
from app.database import db_manager
from app.models.schema import QueueItemModel
<<<<<<< HEAD
from app.security.validators import (
    check_host_lock_permission,
    sanitize_and_validate_attachment,
    sanitize_discord_outbound_text,
)
=======
from app.security.validators import check_host_lock_permission, sanitize_and_validate_attachment
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
from app.services.academy_service import AcademyService
from app.services.backup_service import BackupService
from app.services.leveling_service import LevelingService
from app.services.lyrics_service import LyricsService, lyrics_service as default_lyrics_service
from app.services.music_service import (
    DEFAULT_STREAM_USER_AGENT,
    TrackCandidate,
    classify_music_input,
<<<<<<< HEAD
    download_playable_audio_file_ytdlp,
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    extract_playable_stream_ytdlp,
    extract_spotify_playlist_tracks,
    get_verified_radios,
    invalidate_stream_cache,
    recommend_autoplay_tracks,
    resolve_spotify_link,
    resolve_youtube_link,
    search_songs_with_singer,
)
from app.services.queue import GuildQueueService, queue_service as default_queue_service

logger = logging.getLogger("athenaa.bot")


SLASH_COMMAND_SPECIFICATIONS: List[Dict[str, str]] = [
    {"name": "/play", "params": "query", "category": "Musik", "description": "Putar lagu dari judul/penyanyi, URL YouTube, Spotify Track/Playlist, atau Radio"},
    {"name": "/search", "params": "query", "category": "Musik", "description": "Cari lagu dan tampilkan daftar pilihan beserta nama penyanyi"},
    {"name": "/queue", "params": "[page]", "category": "Musik", "description": "Tampilkan daftar antrean lagu aktif dengan progress bar modern"},
    {"name": "/remove", "params": "posisi", "category": "Musik", "description": "Hapus lagu tertentu dari daftar antrean berdasarkan nomor urut"},
    {"name": "/nowplaying", "params": "", "category": "Musik", "description": "Tampilkan panel lagu yang sedang diputar beserta tombol kontrol interaktif"},
    {"name": "/skip", "params": "", "category": "Musik", "description": "Lewati lagu saat ini di Voice Channel"},
    {"name": "/stop", "params": "", "category": "Musik", "description": "Hentikan pemutaran dan bersihkan antrean"},
    {"name": "/pause", "params": "", "category": "Musik", "description": "Jeda pemutaran lagu aktif"},
    {"name": "/resume", "params": "", "category": "Musik", "description": "Lanjutkan pemutaran lagu yang dijeda"},
    {"name": "/shuffle", "params": "", "category": "Musik", "description": "Acak urutan antrean musik"},
    {"name": "/volume", "params": "persen (1-100)", "category": "Musik", "description": "Atur volume suara bot antara 1% hingga 100%"},
    {"name": "/loop", "params": "mode (off|one|queue)", "category": "Musik", "description": "Atur mode pengulangan lagu atau antrean"},
    {"name": "/autoplay", "params": "aktif (true|false)", "category": "Musik", "description": "Aktifkan/nonaktifkan pencarian lagu lanjutan otomatis saat antrean habis"},
    {"name": "/247", "params": "aktif (true|false)", "category": "Musik", "description": "Pertahankan koneksi bot di voice channel selama 24/7"},
    {"name": "/lyrics", "params": "[judul]", "category": "Musik", "description": "Tampilkan lirik tersinkronisasi atau teks dari LRCLIB"},
    {"name": "/leave", "params": "", "category": "Musik", "description": "Putuskan koneksi voice channel"},
    {"name": "/tugas", "params": "", "category": "Akademik", "description": "Lihat daftar tugas kuliah aktif beserta countdown deadline WIB & file modul"},
    {"name": "/tugas_list", "params": "", "category": "Akademik", "description": "Lihat daftar tugas kuliah aktif beserta countdown deadline WIB & file modul"},
    {"name": "/tugas_add", "params": "mata_kuliah judul deadline_iso [file_modul]", "category": "Akademik", "description": "Tambahkan tugas akademik baru secara manual beserta lampiran modul"},
    {"name": "/tugas_done", "params": "task_id", "category": "Akademik", "description": "Tandai tugas selesai dan hentikan reminder berikutnya"},
    {"name": "/tugas_hapus", "params": "task_id", "category": "Akademik", "description": "Hapus tugas dari database berdasarkan ID Tugas"},
    {"name": "/sync_waskita", "params": "[ical_url]", "category": "Akademik", "description": "Sinkronkan tugas Waskita/Moodle yang dapat di-turn in (Auto-Sync tiap 1 jam)"},
    {"name": "/pomodoro", "params": "[fokus_menit] [istirahat_menit] [topik]", "category": "Mahasiswa", "description": "Mulai timer fokus belajar Pomodoro interaktif di Discord (+30 EXP)"},
    {"name": "/ipk", "params": "sks_nilai", "category": "Mahasiswa", "description": "Hitung simulasi IP/IPK semester dari format SKS:Nilai (mis. 3:A, 4:AB, 3:B+)"},
    {"name": "/kelompok", "params": "jumlah_kelompok [daftar_nama]", "category": "Mahasiswa", "description": "Acak pembagian kelompok tugas dari daftar nama atau anggota Voice Channel"},
    {"name": "/level", "params": "[member]", "category": "Leaderboard & AFK", "description": "Lihat kartu profil Level, progres EXP, dan sumber EXP (Chat & Voice)"},
    {"name": "/leaderboard", "params": "", "category": "Leaderboard & AFK", "description": "Tampilkan Top 15 Leaderboard Server (Chat, Join Voice, Speak, Listen, Stream)"},
    {"name": "/afk", "params": "[alasan]", "category": "Leaderboard & AFK", "description": "Pasang status AFK dengan alasan opsional"},
    {"name": "/kuis", "params": "", "category": "Minigames", "description": "Mainkan kuis interaktif pilihan ganda dengan tombol A/B/C/D (+25 EXP)"},
    {"name": "/mathbattle", "params": "", "category": "Minigames", "description": "Tantangan hitung cepat matematika dengan tombol interaktif (+20 EXP)"},
    {"name": "/suit", "params": "pilihan (batu|gunting|kertas)", "category": "Minigames", "description": "Mainkan suit Batu-Gunting-Kertas melawan Athenaa (+15 EXP)"},
    {"name": "/8ball", "params": "pertanyaan", "category": "Minigames", "description": "Tanyakan pertanyaan ke Kerang Ajaib Athenaa"},
    {"name": "/dadu", "params": "[sisi]", "category": "Minigames", "description": "Lempar dadu keberuntungan (d6, d20, d100)"},
    {"name": "/invite", "params": "", "category": "Utilitas", "description": "Tampilkan tautan resmi untuk mengundang Athenaa Bot ke server Discord lain"},
    {"name": "/admin", "params": "aksi", "category": "Admin Server", "description": "Panel Admin Server (Backup SQLite, Sync Slash Commands, Reset Voice)"},
]


TRIVIA_QUESTIONS: List[Dict[str, Any]] = [
    {
        "category": "Jaringan Komputer",
        "question": "Protokol transport layer manakah yang menggunakan mekanisme Three-Way Handshake (SYN, SYN-ACK, ACK)?",
        "options": ["A. UDP", "B. TCP", "C. ICMP", "D. ARP"],
        "correct_index": 1,
        "explanation": "TCP (Transmission Control Protocol) bersifat connection-oriented dan memulai sesi melalui 3-way handshake.",
    },
    {
        "category": "Struktur Data & Algoritma",
        "question": "Berapakah kompleksitas waktu rata-rata (average case) dari algoritma pencarian Binary Search pada array terurut?",
        "options": ["A. O(1)", "B. O(n)", "C. O(log n)", "D. O(n log n)"],
        "correct_index": 2,
        "explanation": "Binary Search membagi ruang pencarian menjadi dua pada setiap langkah sehingga memiliki kompleksitas O(log n).",
    },
    {
        "category": "Basis Data",
        "question": "Bentuk normal manakah yang mengharuskan setiap determinan merupakan candidate key?",
        "options": ["A. 1NF", "B. 2NF", "C. BCNF (Boyce-Codd Normal Form)", "D. Unnormalized"],
        "correct_index": 2,
        "explanation": "Pada BCNF, untuk setiap ketergantungan fungsional X -> Y yang non-trivial, X wajib merupakan superkey/candidate key.",
    },
    {
        "category": "Sistem Operasi",
        "question": "Kondisi di mana dua atau lebih proses saling menunggu sumber daya tanpa batas waktu disebut?",
        "options": ["A. Paging", "B. Deadlock", "C. Context Switch", "D. Thrashing"],
        "correct_index": 1,
        "explanation": "Deadlock terjadi ketika 4 syarat Coffman terpenuhi: Mutual Exclusion, Hold & Wait, No Preemption, dan Circular Wait.",
    },
    {
        "category": "Keamanan Siber",
        "question": "Serangan yang memaksa server aplikasi melakukan request HTTP ke jaringan internal/localhost (127.0.0.1) disebut?",
        "options": ["A. XSS", "B. CSRF", "C. SSRF (Server-Side Request Forgery)", "D. SQL Injection"],
        "correct_index": 2,
        "explanation": "SSRF mengeksploitasi server agar mengakses resource internal; dicegah dengan memblokir IP loopback & private.",
    },
    {
        "category": "Pengetahuan Umum & Sains",
        "question": "Satuan frekuensi suara yang mengukur jumlah siklus gelombang audio per detik adalah?",
        "options": ["A. Desibel (dB)", "B. Hertz (Hz)", "C. Watt (W)", "D. Ohm (Ω)"],
        "correct_index": 1,
        "explanation": "Hertz (Hz) adalah satuan SI untuk frekuensi (1 Hz = 1 siklus per detik).",
    },
]


def _format_mmss(seconds: int) -> str:
    sec = max(0, int(seconds))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _build_progress_bar(current: int, total: int, length: int = 14) -> str:
    total_safe = max(1, int(total))
    curr_safe = max(0, min(int(current), total_safe))
    filled = int(round((curr_safe / total_safe) * length))
    bar = "▰" * filled + "▱" * max(0, length - filled)
    pct = int(round((curr_safe / total_safe) * 100))
    return f"`{bar}` **{pct}%**"


def _source_badge(source_type: str) -> str:
    st = (source_type or "").lower()
    if st == "youtube":
        return "🔴 YouTube Direct"
    if "radio" in st:
        return "📻 Live Radio Stream"
    return "🟢 Spotify"


def _format_wib_deadline_and_countdown(deadline_iso: str, now_ref: Optional[datetime] = None) -> tuple[str, str]:
    """
    Mengonversi string ISO deadline ke format waktu WIB yang akurat beserta hitung mundur faktual.
    Tidak pernah mengarang informasi di luar timestamp deadline asli.
    """
    try:
        wib_tz = ZoneInfo("Asia/Jakarta")
    except Exception:
        wib_tz = timezone(timedelta(hours=7))
    now_wib = (now_ref or datetime.now(timezone.utc)).astimezone(wib_tz)
    try:
        dl = datetime.fromisoformat(deadline_iso)
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=wib_tz)
        else:
            dl = dl.astimezone(wib_tz)
        formatted = dl.strftime("%d %b %Y • %H:%M WIB")
        diff_sec = int((dl - now_wib).total_seconds())
        if diff_sec <= 0:
            return formatted, "⚠️ Tenggat waktu telah tiba"
        days = diff_sec // 86400
        hours = (diff_sec % 86400) // 3600
        mins = (diff_sec % 3600) // 60
        if days > 0:
            countdown = f"⏳ {days} hari {hours} jam lagi"
        elif hours > 0:
            countdown = f"⏳ {hours} jam {mins} menit lagi"
        else:
            countdown = f"🚨 {mins} menit lagi"
        return formatted, countdown
    except Exception:
        return deadline_iso[:16].replace("T", " ") + " WIB", "⏳ Menunggu tenggat"


def _collect_task_module_files(
    guild_id: str,
    task_ids: Optional[List[str]] = None,
    max_files: int = 10,
) -> Tuple[List[Any], List[Dict[str, str]]]:
    """
    Mengambil file fisik modul dari tabel task_attachments dan membungkusnya
    menjadi objek discord.File agar langsung terkirim sebagai lampiran di Discord.
    """
    discord_files: List[Any] = []
    meta_list: List[Dict[str, str]] = []

    try:
        with db_manager.transaction() as conn:
            if task_ids:
                placeholders = ",".join("?" for _ in task_ids)
                rows = conn.execute(
                    f"""
                    SELECT * FROM task_attachments
                    WHERE guild_id = ? AND (task_id IN ({placeholders}) OR task_id = '')
                    ORDER BY created_at DESC
                    """,
                    (str(guild_id), *[str(tid) for tid in task_ids]),
                ).fetchall()
                if not rows:
                    rows = conn.execute(
                        "SELECT * FROM task_attachments WHERE guild_id = ? ORDER BY created_at DESC",
                        (str(guild_id),),
                    ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM task_attachments WHERE guild_id = ? ORDER BY created_at DESC",
                    (str(guild_id),),
                ).fetchall()
    except Exception:
        rows = []

    seen_stored: Set[str] = set()
    for row in rows:
        if len(discord_files) >= max_files:
            break
        row_d = dict(row)
        stored_name = Path(str(row_d.get("stored_filename") or "")).name
        if not stored_name or stored_name in seen_stored:
            continue
        seen_stored.add(stored_name)

        orig_name = str(row_d.get("original_filename") or stored_name or "modul.pdf")
        task_id_ref = str(row_d.get("task_id") or "-")

        candidate_paths: List[Path] = []
        if getattr(settings, "modules_dir", None):
            candidate_paths.append(Path(settings.modules_dir) / stored_name)
        candidate_paths.extend(
            [
                Path("modules") / stored_name,
                Path("data/modules") / stored_name,
                Path(__file__).resolve().parents[2] / "modules" / stored_name,
            ]
        )

        found_path: Optional[Path] = None
        for fp in candidate_paths:
            if fp.is_file() and fp.stat().st_size > 0:
                found_path = fp
                break

        if found_path is None:
            try:
                from app.web.routes.api import _build_valid_pdf_bytes

                fallback_dir = Path(getattr(settings, "modules_dir", None) or Path("modules"))
                fallback_dir.mkdir(parents=True, exist_ok=True)
                fallback_fp = fallback_dir / stored_name
                pdf_bytes = _build_valid_pdf_bytes(
                    orig_name,
                    str(row_d.get("uploaded_by") or "Aetheriaaa"),
                    str(row_d.get("attachment_id") or "att"),
                )
                fallback_fp.write_bytes(pdf_bytes)
                found_path = fallback_fp
            except Exception:
                found_path = None

        if found_path and found_path.is_file():
            try:
                if DISCORD_PY_AVAILABLE:
                    discord_files.append(discord.File(str(found_path), filename=orig_name))
                meta_list.append(
                    {
                        "original_filename": orig_name,
                        "task_id": task_id_ref,
                        "uploaded_by": str(row_d.get("uploaded_by") or "Aetheriaaa"),
                    }
                )
            except Exception:
                pass

    return discord_files, meta_list


def build_daily_task_reminder_embed(
    tasks: List[Any],
    date_wib_str: str,
    now_ref: Optional[datetime] = None,
    module_metas: Optional[List[Dict[str, str]]] = None,
) -> discord.Embed:
    """
    Membangun Discord Embed modern untuk Pengingat Tugas Harian (00:01 WIB) Waskita/Moodle.
    100% faktual berdasarkan field nyata dari database (`course_name`, `title`, `deadline_iso`, `source_url`, `task_id`).
    """
    emb = discord.Embed(
        title=f"🎓 Pengingat Tugas Akademik & Waskita ({len(tasks)} Tugas Aktif)",
        description=(
            f"📅 **Jadwal Pengingat Harian:** `{date_wib_str} • 00:01 WIB`\n"
            f"🔄 **Sinkronisasi Waskita/Moodle:** Otomatis setiap **1 Jam** (Tugas lewat tenggat otomatis dihapus).\n"
            f"Berikut adalah daftar tugas aktif yang belum diselesaikan berdasarkan data kalender akademik:"
        ),
        color=discord.Color(0x38BDF8),
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_author(name="✦ Athenaa Academic & Waskita Reminder • 00:01 WIB")

    for idx, t in enumerate(tasks[:12], start=1):
        dl_str, countdown_str = _format_wib_deadline_and_countdown(t.deadline_iso, now_ref=now_ref)
        src_badge = "Waskita / Moodle" if t.source_type == "moodle_ics" else "Tugas Manual"
        field_lines = [
            f"⏰ **Tenggat:** `{dl_str}` ({countdown_str})",
            f"🏷️ **Sumber:** `{src_badge}` • 🆔 `{t.task_id}`",
        ]
        if getattr(t, "description", ""):
            clean_desc = str(t.description).strip()
            if clean_desc:
                short_desc = clean_desc[:140] + ("..." if len(clean_desc) > 140 else "")
                field_lines.append(f"📝 **Catatan:** {short_desc}")
        if getattr(t, "source_url", "") and str(t.source_url).startswith(("http://", "https://")):
            field_lines.append(f"🔗 [Buka Pengumpulan Tugas (Turn-In)]({t.source_url})")

        emb.add_field(
            name=f"`#{idx}` [{t.course_name}] {t.title}",
            value="\n".join(field_lines),
            inline=False,
        )

    if module_metas:
        mod_summary = "\n".join(
            f"📎 **{m['original_filename']}** *(Tugas: `{m['task_id']}` • oleh {m['uploaded_by']})*"
            for m in module_metas[:8]
        )
        emb.add_field(
            name=f"📂 File Modul Terlampir ({len(module_metas)} File)",
            value=mod_summary,
            inline=False,
        )

    emb.set_footer(
        text="Athenaa Academic Sync • Gunakan /tugas_done <id> jika tugas sudah dikumpulkan"
    )
    return emb


<<<<<<< HEAD
def _ensure_opus_loaded() -> bool:
    """
    Memastikan library native libopus termuat oleh discord.opus di Linux/Pterodactyl
    meskipun ctypes.util.find_library('opus') mengembalikan None pada container minimalis.
    """
    if not DISCORD_PY_AVAILABLE:
        return False
    try:
        if hasattr(discord, "opus") and discord.opus.is_loaded():
            return True
    except Exception:
        pass

    import glob

    candidate_libs: List[str] = [
        "libopus.so.0",
        "libopus.so",
        "opus",
        "/usr/lib/x86_64-linux-gnu/libopus.so.0",
        "/lib/x86_64-linux-gnu/libopus.so.0",
        "/usr/lib/aarch64-linux-gnu/libopus.so.0",
        "/lib/aarch64-linux-gnu/libopus.so.0",
        "/usr/lib/libopus.so.0",
        "/lib/libopus.so.0",
        "libopus-0.dll",
        "libopus.0.dylib",
    ]
    for pattern in ("/usr/lib*/**/libopus.so*", "/lib*/**/libopus.so*", "/usr/local/lib*/**/libopus.so*"):
        try:
            for found in glob.glob(pattern, recursive=True):
                if found not in candidate_libs:
                    candidate_libs.append(found)
        except Exception:
            pass

    for lib_path in candidate_libs:
        try:
            discord.opus.load_opus(lib_path)
            if discord.opus.is_loaded():
                logger.info("Library Opus untuk Discord Voice berhasil dimuat dari: %s", lib_path)
                return True
        except Exception:
            continue
    return False


def _needs_stream_extraction(url: Optional[str]) -> bool:
    """Memeriksa apakah URL belum berupa direct audio stream / file lokal dan masih perlu diekstrak."""
    if not url or not isinstance(url, str):
        return True
    cleaned = url.strip()
    if not cleaned:
        return True
    if cleaned.startswith("/") and Path(cleaned).is_file():
        return False
=======
def _needs_stream_extraction(url: Optional[str]) -> bool:
    """Memeriksa apakah URL belum berupa direct audio stream dan masih perlu diekstrak."""
    if not url or not isinstance(url, str):
        return True
    cleaned = url.strip()
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    if not cleaned.startswith(("http://", "https://")):
        return True
    lowered = cleaned.lower()
    webpage_domains = (
        "youtube.com/watch",
        "youtube.com/shorts",
        "youtube.com/playlist",
        "music.youtube.com/",
        "youtu.be/",
        "open.spotify.com/",
        "spotify.com/",
        "soundcloud.com/",
    )
    return any(dom in lowered for dom in webpage_domains)


def _build_track_stream_query(track_obj: Any) -> str:
    src = str(getattr(track_obj, "source_url", "") or "").strip()
    if src and ("youtube.com/watch" in src or "youtu.be/" in src):
        return src
    t_title = str(getattr(track_obj, "title", "") or "").strip()
    t_artist = str(getattr(track_obj, "artist", "") or "").strip()
    if t_artist and t_artist.lower() not in ("spotify artist", "unknown artist", "youtube music"):
        return f"{t_artist} - {t_title}".strip()
    return t_title or src


def _fetch_youtube_alt_stream_fallback(title: str, artist: str) -> Optional[Dict[str, Any]]:
    """
    Fallback pencarian direct audio stream melalui YouTube HTTP Search + yt-dlp
    apabila query utama gagal diekstrak (menjaga kecocokan versi original vs DJ/Remix/Slowed).
    """
    clean_t = (title or "").strip()
    clean_a = (artist or "").strip()
    query = f"{clean_a} - {clean_t}".strip(" -") if clean_a and clean_a.lower() != "spotify artist" else clean_t
    if not query:
        return None
    try:
        candidates = search_songs_with_singer(query, limit=3)
        for cand in candidates:
            if cand.source_url and ("youtube.com/watch" in cand.source_url or "youtu.be/" in cand.source_url):
                info = extract_playable_stream_ytdlp(cand.source_url)
                if info and info.get("stream_url") and not _needs_stream_extraction(str(info["stream_url"])):
                    return {
                        "stream_url": str(info["stream_url"]),
                        "duration_sec": int(info.get("duration_sec") or cand.duration_sec or 0),
                        "thumbnail_url": str(info.get("thumbnail_url") or cand.thumbnail_url or ""),
<<<<<<< HEAD
                        "cookies": str(info.get("cookies") or ""),
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                    }
    except Exception as exc:
        logger.debug("Fallback YouTube stream gagal untuk '%s': %s", query, exc)
    return None


def build_discord_bot(
    queue_service: Optional[GuildQueueService] = None,
    academy_service: Optional[AcademyService] = None,
    leveling_service: Optional[LevelingService] = None,
    lyrics_service: Optional[LyricsService] = None,
    backup_service: Optional[BackupService] = None,
    on_state_change: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None,
):
    """
    Membangun instance commands.Bot discord.py dengan Voice Audio Engine nyata,
    Modern Embeds, Voice EXP Tracking, dan Addon Mahasiswa/Minigames.
    """
    queue_service = queue_service or default_queue_service
    academy_service = academy_service or AcademyService()
    leveling_service = leveling_service or LevelingService()
    lyrics_service = lyrics_service or default_lyrics_service
    backup_service = backup_service or BackupService()

    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    intents.guilds = True
    intents.members = True

    def _make_embed(
        title: str,
        description: str = "",
        color: int = 0xDC95FF,
        category_label: str = "Athenaa Music & Academy Hub",
        thumbnail_url: str = "",
        footer_text: str = "Athenaa Bot • Sinkron Real-Time dengan Web Player",
    ) -> discord.Embed:
        emb = discord.Embed(
            title=title,
            description=description,
            color=discord.Color(color),
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_author(name=f"✦ {category_label}")
        if thumbnail_url and thumbnail_url.startswith(("http://", "https://")):
            emb.set_thumbnail(url=thumbnail_url)
        emb.set_footer(text=footer_text)
        return emb

    class TriviaQuizView(discord.ui.View):
        def __init__(self, q_data: Dict[str, Any], guild_id: str):
            super().__init__(timeout=45.0)
            self.q_data = q_data
            self.guild_id = guild_id
            self.answered_users: set[int] = set()

            labels = ["A", "B", "C", "D"]
            for idx, lbl in enumerate(labels):
                btn = discord.ui.Button(
                    label=lbl,
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"quiz_ans_{idx}",
                )
                btn.callback = self._make_callback(idx)
                self.add_item(btn)

        def _make_callback(self, chosen_idx: int):
            async def callback(interaction: discord.Interaction):
                if interaction.user.id in self.answered_users:
                    await interaction.response.send_message(
                        "⚠️ Kamu sudah menjawab kuis ini! Gunakan `/kuis` lagi untuk soal berikutnya.",
                        ephemeral=True,
                    )
                    return
                self.answered_users.add(interaction.user.id)
                correct_idx = int(self.q_data["correct_index"])
                is_correct = chosen_idx == correct_idx

                if is_correct:
                    leveled_up, lvl, c_exp, m_exp = leveling_service.process_voice_activity(
                        guild_id=self.guild_id,
                        user_id=str(interaction.user.id),
                        username=interaction.user.name,
                        display_name=interaction.user.display_name,
                        activity_type="minigame",
                        cooldown_seconds=5,
                        exp_gain=25,
                    )
                    for idx_item, child in enumerate(self.children):
                        if isinstance(child, discord.ui.Button):
                            child.disabled = True
                            if idx_item == correct_idx:
                                child.style = discord.ButtonStyle.success
                    win_emb = _make_embed(
                        title="🎉 Jawaban Benar! (+25 EXP)",
                        description=(
                            f"**{interaction.user.display_name}** menjawab dengan tepat!\n\n"
                            f"📘 **Pembahasan:** {self.q_data['explanation']}\n"
                            f"🏆 **Status Level:** Level **{lvl}** ({c_exp}/{m_exp} EXP)"
                            + ("\n✨ **LEVEL UP!** Selamat kamu naik level!" if leveled_up else "")
                        ),
                        color=0xDC95FF,
                        category_label=f"Kuis Interaktif • {self.q_data['category']}",
                    )
                    await interaction.response.edit_message(embed=win_emb, view=self)
                else:
                    wrong_emb = _make_embed(
                        title="❌ Jawaban Kurang Tepat!",
                        description=(
                            f"Pilihan **{interaction.user.display_name}** belum tepat.\n"
                            f"Jawaban yang benar adalah **{self.q_data['options'][correct_idx]}**.\n\n"
                            f"📘 **Pembahasan:** {self.q_data['explanation']}"
                        ),
                        color=0xEF4444,
                        category_label=f"Kuis Interaktif • {self.q_data['category']}",
                    )
                    await interaction.response.send_message(embed=wrong_emb, ephemeral=True)

            return callback

    class MathBattleView(discord.ui.View):
        def __init__(self, expr_str: str, correct_val: int, options: List[int], guild_id: str):
            super().__init__(timeout=30.0)
            self.expr_str = expr_str
            self.correct_val = correct_val
            self.guild_id = guild_id
            self.solved = False

            for opt in options:
                btn = discord.ui.Button(
                    label=str(opt),
                    style=discord.ButtonStyle.primary,
                )
                btn.callback = self._make_callback(opt)
                self.add_item(btn)

        def _make_callback(self, val: int):
            async def callback(interaction: discord.Interaction):
                if self.solved:
                    await interaction.response.send_message("Soal ini sudah terjawab!", ephemeral=True)
                    return
                if val == self.correct_val:
                    self.solved = True
                    for child in self.children:
                        if isinstance(child, discord.ui.Button):
                            child.disabled = True
                            if child.label == str(self.correct_val):
                                child.style = discord.ButtonStyle.success
                    leveled_up, lvl, c_exp, m_exp = leveling_service.process_voice_activity(
                        guild_id=self.guild_id,
                        user_id=str(interaction.user.id),
                        username=interaction.user.name,
                        display_name=interaction.user.display_name,
                        activity_type="minigame",
                        cooldown_seconds=5,
                        exp_gain=20,
                    )
                    emb = _make_embed(
                        title="⚡ Math Battle Dimenangkan! (+20 EXP)",
                        description=(
                            f"**{interaction.user.display_name}** berhasil menghitung paling cepat!\n\n"
                            f"🧮 `{self.expr_str} = {self.correct_val}`\n"
                            f"🏆 **Level Saat Ini:** Lv. **{lvl}** ({c_exp}/{m_exp} EXP)"
                            + ("\n✨ **LEVEL UP!**" if leveled_up else "")
                        ),
                        color=0xDC95FF,
                        category_label="Athenaa Minigames • Math Battle",
                    )
                    await interaction.response.edit_message(embed=emb, view=self)
                else:
                    await interaction.response.send_message(
                        f"❌ `{val}` bukan jawaban yang tepat! Coba hitung lagi.",
                        ephemeral=True,
                    )

            return callback

    class AthenaaDiscordBot(commands.Bot):
        def __init__(self) -> None:
            super().__init__(command_prefix="!", intents=intents)
            queue_service.voice_bot_active = True
            self._guild_locks: Dict[str, asyncio.Lock] = {}
            self._position_task: Optional[asyncio.Task] = None
            self._voice_exp_task: Optional[asyncio.Task] = None
            self._waskita_sync_task: Optional[asyncio.Task] = None
            self._daily_reminder_task: Optional[asyncio.Task] = None
            self._voice_connect_locks: Dict[str, asyncio.Lock] = {}
            self._active_vc_track_id: Dict[str, str] = {}
            self._active_vc_volume: Dict[str, int] = {}
            self._track_user_agents: Dict[str, str] = {}
            self._syncing_track_key: Dict[str, str] = {}
            self._playback_gen: Dict[str, int] = {}
            self._last_sync_attempt: Dict[str, float] = {}
            self._track_started_mono: Dict[str, float] = {}
            self._track_pause_mono: Dict[str, float] = {}
            self._track_stopped_mono: Dict[str, float] = {}
            self._last_web_pos_notify: Dict[str, float] = {}
            self._prefetch_tasks: Dict[str, asyncio.Task] = {}
            queue_service.register_listener(self._on_queue_event)

        def _get_lock(self, guild_id: str) -> asyncio.Lock:
            if guild_id not in self._guild_locks:
                self._guild_locks[guild_id] = asyncio.Lock()
            return self._guild_locks[guild_id]

        def _get_connect_lock(self, guild_id: str) -> asyncio.Lock:
            if guild_id not in self._voice_connect_locks:
                self._voice_connect_locks[guild_id] = asyncio.Lock()
            return self._voice_connect_locks[guild_id]

        async def _notify_web(self, guild_id: str) -> None:
            try:
                queue_service.notify_listeners(guild_id, "voice_sync")
            except Exception as exc:
                logger.debug("Gagal memberi tahu listener queue: %s", exc)
            if on_state_change is not None:
                try:
                    await on_state_change(guild_id)
                except Exception as exc:
                    logger.debug("Gagal mengirim broadcast WS: %s", exc)

        def _schedule_prefetch(self, guild_id: str) -> None:
            """
            Mengekstrak stream_url di background untuk 1 lagu berikutnya secara tertunda (deferred 5 detik)
            setelah buffer FFmpeg stabil, serta menyiapkan kandidat Autoplay terkait dari YouTube apabila antrean kosong.
            """
            loop = self.loop
            if not loop or not loop.is_running():
                return
            existing = self._prefetch_tasks.get(guild_id)
            if existing and not existing.done():
                return

            async def _prefetch_worker() -> None:
                try:
                    await asyncio.sleep(5.0)
                    st = queue_service.get_state(guild_id)
                    if st.is_loading_stream:
                        await asyncio.sleep(3.0)

                    candidates = list(st.queue[:1])
                    for q_item in candidates:
                        if not _needs_stream_extraction(q_item.stream_url):
                            continue
                        target_q = _build_track_stream_query(q_item)
                        info = await asyncio.to_thread(extract_playable_stream_ytdlp, target_q)
                        if info and info.get("stream_url") and not _needs_stream_extraction(str(info["stream_url"])):
                            q_item.stream_url = str(info["stream_url"])
                            if info.get("user_agent"):
                                self._track_user_agents[q_item.item_id] = str(info["user_agent"])
                            if info.get("duration_sec") and int(info["duration_sec"]) > 0 and not q_item.duration_sec:
                                q_item.duration_sec = int(info["duration_sec"])
                            if info.get("thumbnail_url") and not q_item.thumbnail_url:
                                q_item.thumbnail_url = str(info["thumbnail_url"])

                    if (
                        st.autoplay
                        and not st.queue
                        and st.current_track
                        and st.current_track.source_type != "radio"
                        and not queue_service.prefetched_autoplay.get(guild_id)
                    ):
                        seed_tr = st.current_track
                        auto_cands = await asyncio.to_thread(
                            queue_service._build_default_autoplay_candidates,
                            guild_id,
                            seed_tr,
                            True,
                        )
                        if auto_cands:
                            first_auto = auto_cands[0]
                            auto_q = _build_track_stream_query(first_auto)
                            auto_info = await asyncio.to_thread(extract_playable_stream_ytdlp, auto_q)
                            if auto_info and auto_info.get("stream_url") and not _needs_stream_extraction(str(auto_info["stream_url"])):
                                first_auto.stream_url = str(auto_info["stream_url"])
                                if auto_info.get("user_agent"):
                                    self._track_user_agents[first_auto.item_id] = str(auto_info["user_agent"])
                                if auto_info.get("duration_sec") and int(auto_info["duration_sec"]) > 0:
                                    first_auto.duration_sec = int(auto_info["duration_sec"])
                                if auto_info.get("thumbnail_url"):
                                    first_auto.thumbnail_url = str(auto_info["thumbnail_url"])
                            queue_service.set_prefetched_autoplay(guild_id, auto_cands)
                except Exception as exc:
                    logger.debug("Prefetch antrean guild %s selesai dengan catatan: %s", guild_id, exc)

            try:
                self._prefetch_tasks[guild_id] = loop.create_task(_prefetch_worker())
            except Exception:
                pass

        def _is_unplayed_seed_track(self, guild_id: str, st: Any) -> bool:
            """Mendeteksi apakah current_track masih berupa data dummy/seed bawaan saat boot yang belum diputar di Voice."""
            tr = getattr(st, "current_track", None)
            if not tr:
                return False
            tr_id = str(getattr(tr, "item_id", "") or getattr(tr, "id", "") or "")
            if self._active_vc_track_id.get(guild_id) == tr_id and tr_id:
                return False
            tr_title = str(getattr(tr, "title", "") or "").strip().lower()
            pos_sec = int(getattr(st, "position_sec", 0) or 0)
            if tr_id.startswith("trk-seed") or (tr_title == "cincin" and pos_sec == 74):
                return True
            return False

        def _schedule_coro(self, coro: Coroutine[Any, Any, Any]) -> None:
            loop = getattr(self, "loop", None)
            if not loop:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
            if loop and loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(coro, loop)
                def _log_future_err(f: Any) -> None:
                    try:
                        exc = f.exception()
                        if exc:
                            logger.error("Error pada task sinkronisasi VoiceClient: %s", exc)
                    except Exception:
                        pass
                fut.add_done_callback(_log_future_err)
            else:
                try:
                    coro.close()
                except Exception:
                    pass

        def _on_queue_event(self, guild_id: str, state_or_event: Any, event_or_payload: Any = None) -> None:
            if self.is_closed():
                return
            event_type = (
                event_or_payload
                if isinstance(event_or_payload, str)
                else (state_or_event if isinstance(state_or_event, str) else "state_update")
            )
            if event_type == "voice_sync":
                return

            try:
                st_curr = queue_service.get_state(guild_id)
                vc_guild = self.get_guild(int(guild_id)) if guild_id.isdigit() else None
                vc: Optional[discord.VoiceClient] = vc_guild.voice_client if vc_guild else None  # type: ignore

                if self._is_unplayed_seed_track(guild_id, st_curr) and st_curr.queue:
                    queue_service.advance_track(guild_id)
                    st_curr = queue_service.get_state(guild_id)

                if event_type in ("track_started", "skipped"):
                    if st_curr.current_track:
                        active_tid = self._active_vc_track_id.get(guild_id)
                        if active_tid != st_curr.current_track.item_id or event_type == "skipped":
                            self._playback_gen[guild_id] = self._playback_gen.get(guild_id, 0) + 1
                            self._active_vc_track_id.pop(guild_id, None)
                            self._syncing_track_key.pop(guild_id, None)
                            self._track_stopped_mono.pop(guild_id, None)
                            if vc and (vc.is_playing() or vc.is_paused()):
                                vc.stop()
                        self._schedule_coro(
                            self.start_or_sync_voice_playback(
                                guild_id,
                                st_curr.current_track.requester_id,
                                seek_seconds=0,
                            )
                        )
                    else:
                        self._schedule_coro(self.apply_web_control(guild_id, "stop"))
                elif event_type in (
                    "track_added",
                    "track_queued",
                    "playlist_played",
                    "playlist_loaded",
                    "queue_updated",
                ):
                    self._schedule_prefetch(guild_id)
                    if st_curr.current_track and not st_curr.is_paused and not st_curr.is_loading_stream:
                        if not vc or not vc.is_connected() or (not vc.is_playing() and not vc.is_paused()):
                            self._schedule_coro(
                                self.start_or_sync_voice_playback(guild_id, st_curr.current_track.requester_id)
                            )
                elif event_type == "paused":
                    if vc and vc.is_playing():
                        vc.pause()
                    self._schedule_coro(self.apply_web_control(guild_id, "pause"))
                elif event_type == "resumed":
                    if vc and vc.is_paused():
                        vc.resume()
                    self._schedule_coro(self.apply_web_control(guild_id, "resume"))
                elif event_type == "stopped":
                    self._playback_gen[guild_id] = self._playback_gen.get(guild_id, 0) + 1
                    self._active_vc_track_id.pop(guild_id, None)
                    self._syncing_track_key.pop(guild_id, None)
                    self._track_stopped_mono.pop(guild_id, None)
                    st_curr.is_loading_stream = False
                    if vc and (vc.is_playing() or vc.is_paused()):
                        vc.stop()
                    self._schedule_coro(self.apply_web_control(guild_id, "stop"))
                elif event_type == "seeked":
                    self._schedule_coro(self.apply_web_control(guild_id, "seek"))
                elif event_type == "volume_changed":
                    self._schedule_coro(self.apply_web_control(guild_id, "volume"))
                elif event_type == "autoplay_changed":
                    self._schedule_coro(self.apply_web_control(guild_id, "autoplay", st_curr.autoplay))
                elif event_type == "mode_247_changed":
                    self._schedule_coro(self.apply_web_control(guild_id, "mode_247", st_curr.mode_247))
            except Exception as exc_cb:
                logger.error("Gagal menyinkronkan event queue (%s) ke VoiceClient: %s", event_type, exc_cb)

        async def setup_hook(self) -> None:
<<<<<<< HEAD
            _ensure_opus_loaded()
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            queue_service.register_listener(self._on_queue_event)

            try:
                synced_global = await self.tree.sync()
                logger.info("Berhasil menyinkronkan %d global slash commands ke Discord.", len(synced_global))
<<<<<<< HEAD
=======
                if settings.main_guild_id and settings.main_guild_id.isdigit():
                    guild_obj = discord.Object(id=int(settings.main_guild_id))
                    self.tree.clear_commands(guild=guild_obj)
                    await self.tree.sync(guild=guild_obj)
                    logger.info(
                        "Berhasil membersihkan duplikasi guild-scoped slash commands pada Guild %s.",
                        settings.main_guild_id,
                    )
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            except Exception as exc:
                logger.warning("Gagal menyinkronkan slash commands: %s", exc)

        def _sync_discord_guild(self, g: Any) -> str:
<<<<<<< HEAD
            """Mendaftarkan/memperbarui server Discord ke SQLite & state memori secara modular per-server."""
=======
            """Mendaftarkan/memperbarui server Discord ke SQLite & state memori serta menginisialisasi voice channel."""
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            gid = str(g.id)
            gname = str(getattr(g, "name", "") or f"Server {gid}")
            queue_service.register_active_guild(gid, gname)
            academy_service.ensure_guild_exists(gid, gname)
            st = queue_service.get_state(gid)
<<<<<<< HEAD
            vc = getattr(g, "voice_client", None)
            if vc and getattr(vc, "is_connected", lambda: False)() and getattr(vc, "channel", None):
                st.voice_channel_id = str(vc.channel.id)
                st.voice_channel_name = vc.channel.name
            elif not st.voice_channel_id or (
                gid != "1428666546942902294" and st.voice_channel_id == "1428666547701809167"
            ):
                voice_channels = getattr(g, "voice_channels", []) or []
                if voice_channels:
                    populated = next(
                        (
                            ch
                            for ch in voice_channels
                            if any(not getattr(m, "bot", False) for m in getattr(ch, "members", []))
                        ),
                        voice_channels[0],
                    )
                    st.voice_channel_id = str(populated.id)
                    st.voice_channel_name = populated.name
            return gid

        async def on_ready(self) -> None:
            _ensure_opus_loaded()
            logger.info("Athenaa Discord Bot aktif sebagai %s (ID: %s)", self.user, getattr(self.user, "id", ""))
            for g in self.guilds:
                gid = self._sync_discord_guild(g)
                try:
                    g_obj = discord.Object(id=g.id)
                    self.tree.clear_commands(guild=g_obj)
                    await self.tree.sync(guild=g_obj)
                except Exception:
                    pass
                await self._notify_web(gid)
=======
            voice_channels = getattr(g, "voice_channels", []) or []
            for vc in voice_channels:
                if any(not getattr(m, "bot", False) for m in getattr(vc, "members", [])):
                    st.voice_channel_id = str(vc.id)
                    st.voice_channel_name = vc.name
                    break
            if (not st.voice_channel_id or not str(st.voice_channel_id).isdigit()) and voice_channels:
                st.voice_channel_id = str(voice_channels[0].id)
                st.voice_channel_name = voice_channels[0].name
            return gid

        async def on_ready(self) -> None:
            logger.info("Athenaa Discord Bot aktif sebagai %s (ID: %s)", self.user, getattr(self.user, "id", ""))
            for g in self.guilds:
                gid = self._sync_discord_guild(g)

                if gid != str(settings.main_guild_id or ""):
                    try:
                        g_obj = discord.Object(id=g.id)
                        self.tree.clear_commands(guild=g_obj)
                        await self.tree.sync(guild=g_obj)
                    except Exception:
                        pass

            await self._notify_web(str(settings.main_guild_id))
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

            if self._position_task is None or self._position_task.done():
                self._position_task = asyncio.create_task(self._playback_ticker_loop())
            if self._voice_exp_task is None or self._voice_exp_task.done():
                self._voice_exp_task = asyncio.create_task(self._voice_exp_loop())
            if self._waskita_sync_task is None or self._waskita_sync_task.done():
                self._waskita_sync_task = asyncio.create_task(self._waskita_hourly_sync_loop())
            if self._daily_reminder_task is None or self._daily_reminder_task.done():
                self._daily_reminder_task = asyncio.create_task(self._daily_0001_wib_reminder_loop())

        async def on_guild_join(self, guild: discord.Guild) -> None:
            gid = self._sync_discord_guild(guild)
            logger.info("Athenaa berhasil ditambahkan ke server Discord baru: %s (ID: %s)", guild.name, gid)
            try:
                g_obj = discord.Object(id=guild.id)
                self.tree.clear_commands(guild=g_obj)
                await self.tree.sync(guild=g_obj)
            except Exception:
                pass
            queue_service.notify_listeners(gid, "guild_join")
            await self._notify_web(gid)

        async def on_guild_update(self, _before: discord.Guild, after: discord.Guild) -> None:
            gid = self._sync_discord_guild(after)
            queue_service.notify_listeners(gid, "guild_update")
            await self._notify_web(gid)

        async def on_guild_remove(self, guild: discord.Guild) -> None:
            gid = str(guild.id)
            queue_service.unregister_active_guild(gid)
            academy_service.remove_guild(gid)
            logger.info("Athenaa keluar dari server Discord: %s (ID: %s)", getattr(guild, "name", gid), gid)
<<<<<<< HEAD
            queue_service.notify_listeners(gid, "guild_remove")
            await self._notify_web(gid)
=======
            queue_service.notify_listeners(str(settings.main_guild_id), "guild_remove")
            await self._notify_web(str(settings.main_guild_id))
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

        async def _playback_ticker_loop(self) -> None:
            """
            Mengupdate posisi detik lagu yang sedang diputar di Discord Voice agar sinkron 100% dengan Web UI,
<<<<<<< HEAD
            tanpa pernah melakukan force-restart lagu yang sudah selesai diputar atau masuk ke channel user lain.
=======
            tanpa pernah melakukan force-restart lagu yang sudah selesai diputar.
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            """
            vc_disconnect_mono: Dict[str, float] = {}

            while not self.is_closed():
                await asyncio.sleep(0.5)
                now_ts = time.monotonic()
                for g in self.guilds:
                    gid = str(g.id)
                    st = queue_service.get_state(gid)
                    vc: Optional[discord.VoiceClient] = g.voice_client  # type: ignore
                    is_vc_connected = bool(vc and vc.is_connected())

                    if is_vc_connected:
                        vc_disconnect_mono.pop(gid, None)
                    elif vc is not None:
                        if gid not in vc_disconnect_mono:
                            vc_disconnect_mono[gid] = now_ts

                    if not is_vc_connected and self._is_unplayed_seed_track(gid, st) and st.queue:
                        queue_service.advance_track(gid)
                        st = queue_service.get_state(gid)

                    if st.is_loading_stream or gid in self._syncing_track_key:
                        continue

                    if is_vc_connected and vc:
                        if not st.current_track or (not st.is_playing and not st.is_paused):
                            self._track_stopped_mono.pop(gid, None)
                            if vc.is_playing() or vc.is_paused():
                                self._playback_gen[gid] = self._playback_gen.get(gid, 0) + 1
                                self._active_vc_track_id.pop(gid, None)
                                vc.stop()
                                await self._notify_web(gid)
                        elif st.is_paused:
                            self._track_stopped_mono.pop(gid, None)
                            if vc.is_playing():
                                vc.pause()
                                await self._notify_web(gid)
                        elif vc.is_playing() and st.current_track and not st.is_paused:
                            self._track_stopped_mono.pop(gid, None)
                            active_tid = self._active_vc_track_id.get(gid)
                            if active_tid and active_tid != st.current_track.item_id:
                                asyncio.create_task(
                                    self.start_or_sync_voice_playback(gid, st.current_track.requester_id)
                                )
                            else:
                                started_m = self._track_started_mono.get(gid)
                                if started_m is None:
                                    started_m = now_ts - float(st.position_sec)
                                    self._track_started_mono[gid] = started_m
                                exact_sec = max(0, int(now_ts - started_m))
                                if st.current_track.duration_sec > 0 and st.current_track.source_type != "radio":
                                    exact_sec = min(st.current_track.duration_sec, exact_sec)
                                if exact_sec != st.position_sec:
                                    st.position_sec = exact_sec
                                    if now_ts - self._last_web_pos_notify.get(gid, 0.0) >= 0.9:
                                        self._last_web_pos_notify[gid] = now_ts
                                        await self._notify_web(gid)
                        elif vc.is_paused() and st.current_track and st.is_playing and not st.is_paused:
                            self._track_stopped_mono.pop(gid, None)
                            vc.resume()
                            await self._notify_web(gid)
                        elif not vc.is_playing() and not vc.is_paused() and st.current_track and st.is_playing and not st.is_paused:
                            active_tid = self._active_vc_track_id.get(gid)
                            if active_tid and active_tid == st.current_track.item_id:
<<<<<<< HEAD
=======
                                # Lagu baru saja selesai diputar di FFmpeg; biarkan callback _after_track memajukan lagu.
                                # Jika dalam 3.5 detik _after_track belum memajukan lagu, panggil _handle_track_finished sebagai fallback aman.
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                                stopped_since = self._track_stopped_mono.setdefault(gid, now_ts)
                                if now_ts - stopped_since >= 3.5:
                                    self._track_stopped_mono.pop(gid, None)
                                    asyncio.create_task(self._handle_track_finished(gid))
                            else:
<<<<<<< HEAD
=======
                                # Lagu aktif di state belum pernah mulai diputar di VoiceClient
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                                self._track_stopped_mono.pop(gid, None)
                                if now_ts - self._last_sync_attempt.get(gid, 0.0) >= 3.5:
                                    self._last_sync_attempt[gid] = now_ts
                                    asyncio.create_task(
                                        self.start_or_sync_voice_playback(
                                            gid,
                                            st.current_track.requester_id,
                                            seek_seconds=0,
                                        )
                                    )
<<<<<<< HEAD
=======
                    else:
                        if vc is not None and (now_ts - vc_disconnect_mono.get(gid, now_ts)) < 15.0:
                            continue

                        if st.current_track and st.is_playing and not st.is_paused:
                            has_humans_in_vc = any(
                                any(not m.bot for m in ch.members) for ch in g.voice_channels
                            )
                            if not self._is_unplayed_seed_track(gid, st) and has_humans_in_vc:
                                if now_ts - self._last_sync_attempt.get(gid, 0.0) >= 8.0:
                                    self._last_sync_attempt[gid] = now_ts
                                    asyncio.create_task(
                                        self.start_or_sync_voice_playback(
                                            gid,
                                            st.current_track.requester_id,
                                            seek_seconds=0,
                                        )
                                    )
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

        async def _voice_exp_loop(self) -> None:
            while not self.is_closed():
                await asyncio.sleep(60.0)
                for g in self.guilds:
                    gid = str(g.id)
                    for vc in g.voice_channels:
                        human_members = [m for m in vc.members if not m.bot]
                        if not human_members:
                            continue
                        for member in human_members:
                            vstate = member.voice
                            if not vstate:
                                continue
                            if (vstate.self_deaf or vstate.deaf) and not (vstate.self_stream or vstate.self_video):
                                continue
                            if vstate.self_stream or vstate.self_video:
                                act_type = "voice_stream"
                                gain = 25
                            elif not vstate.self_mute and not vstate.mute:
                                act_type = "voice_speak"
                                gain = 15
                            else:
                                act_type = "voice_listen"
                                gain = 10

                            leveling_service.process_voice_activity(
                                guild_id=gid,
                                user_id=str(member.id),
                                username=member.name,
                                display_name=member.display_name,
                                activity_type=act_type,
                                is_bot=member.bot,
                                cooldown_seconds=50,
                                exp_gain=gain,
                            )

        def _get_guild_task_channel_id(self, guild_id: str) -> str:
<<<<<<< HEAD
=======
            is_main = str(guild_id or "").strip() == str(settings.main_guild_id or "1428666546942902294").strip()
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            try:
                with academy_service.db.transaction() as conn:
                    row = conn.execute(
                        "SELECT task_channel_id FROM guild_settings WHERE guild_id = ?",
                        (guild_id,),
                    ).fetchone()
                if row and row["task_channel_id"] and str(row["task_channel_id"]).strip():
                    return str(row["task_channel_id"]).strip()
            except Exception:
                pass
<<<<<<< HEAD
            return str(settings.task_reminder_channel_id or "").strip()

        def _get_guild_dj_role_id(self, guild_id: str) -> str:
=======
            return str(settings.task_reminder_channel_id or "").strip() if is_main else ""

        def _get_guild_dj_role_id(self, guild_id: str) -> str:
            is_main = str(guild_id or "").strip() == str(settings.main_guild_id or "1428666546942902294").strip()
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            try:
                with academy_service.db.transaction() as conn:
                    row = conn.execute(
                        "SELECT dj_role_id FROM guild_settings WHERE guild_id = ?",
                        (guild_id,),
                    ).fetchone()
                if row and row["dj_role_id"] and str(row["dj_role_id"]).strip():
                    return str(row["dj_role_id"]).strip()
            except Exception:
                pass
<<<<<<< HEAD
            return str(settings.dj_role_id or "role-dj").strip()
=======
            return str(settings.dj_role_id or "").strip() if is_main else "role-dj"
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

        async def _resolve_discord_text_channel(self, guild: Any, channel_id_str: str) -> Optional[Any]:
            if not channel_id_str or not channel_id_str.isdigit():
                return None
            cid = int(channel_id_str)
<<<<<<< HEAD
            ch = (guild.get_channel(cid) if guild else None) or self.get_channel(cid)
            if ch is None and guild is not None:
                try:
                    ch = await guild.fetch_channel(cid)
=======
            ch = self.get_channel(cid) or (guild.get_channel(cid) if guild else None)
            if ch is None:
                try:
                    ch = await self.fetch_channel(cid)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                except Exception:
                    ch = None
            return ch

        async def _waskita_hourly_sync_loop(self) -> None:
            await asyncio.sleep(5.0)
            while not self.is_closed():
                try:
                    guild_ids = {str(g.id) for g in self.guilds}
<<<<<<< HEAD
                    for gid in guild_ids:
                        saved_ical = academy_service.get_guild_saved_ical_url(gid)
                        has_env_moodle = bool(
=======
                    if settings.main_guild_id:
                        guild_ids.add(str(settings.main_guild_id))
                    for gid in guild_ids:
                        is_main_srv = str(gid).strip() == str(settings.main_guild_id or "1428666546942902294").strip()
                        saved_ical = academy_service.get_guild_saved_ical_url(gid)
                        has_env_moodle = is_main_srv and bool(
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                            settings.moodle_ical_url
                            or (settings.moodle_username and settings.moodle_password)
                        )
                        if not saved_ical and not has_env_moodle:
                            continue
                        res = await asyncio.to_thread(
                            academy_service.sync_moodle_ics_content,
                            gid,
                            "",
                            "Auto-Sync Waskita (1 Jam)",
                            saved_ical,
                            "",
                            "",
                            "",
                            False,
                        )
                        ins = int(res.get("inserted", 0) or 0)
                        upd = int(res.get("updated", 0) or 0)
                        if ins > 0 or upd > 0:
                            logger.info(
                                "Auto-Sync Waskita 1 Jam selesai untuk Guild %s: +%d tugas baru, %d diperbarui.",
                                gid,
                                ins,
                                upd,
                            )
                            await self._notify_web(gid)
                except Exception as exc:
                    logger.debug("Auto-Sync Waskita 1 Jam dilewati dengan catatan: %s", exc)
                await asyncio.sleep(3600.0)

        async def _daily_0001_wib_reminder_loop(self) -> None:
            """
            Mengirim pengingat tugas akademik & Waskita beserta file lampiran modulnya ke channel Discord:
<<<<<<< HEAD
            1. Setiap hari tepat pukul 00:01 AM WIB (Asia/Jakarta, UTC+7) untuk seluruh tugas aktif di tiap server.
=======
            1. Setiap hari tepat pukul 00:01 AM WIB (Asia/Jakarta, UTC+7) untuk seluruh tugas aktif.
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            2. Pengingat H-3 Hari, H-6 Jam, dan H-1 Jam sebelum tenggat waktu.
            """
            wib_tz = ZoneInfo("Asia/Jakarta")
            await asyncio.sleep(8.0)
            while not self.is_closed():
                try:
                    now_utc = datetime.now(timezone.utc)
                    now_wib = now_utc.astimezone(wib_tz)
                    today_wib = now_wib.strftime("%Y-%m-%d")

                    for g in self.guilds:
                        gid = str(g.id)
                        ch_id = self._get_guild_task_channel_id(gid)
                        if not ch_id or not ch_id.isdigit():
                            continue

<<<<<<< HEAD
                        if now_wib.hour == 0 and now_wib.minute >= 1:
                            saved_ical = academy_service.get_guild_saved_ical_url(gid)
                            if saved_ical or settings.moodle_ical_url or (settings.moodle_username and settings.moodle_password):
=======
                        # 1. Evaluasi Jadwal Pengingat Harian Pukul 00:01 WIB
                        if now_wib.hour == 0 and now_wib.minute >= 1:
                            is_main_srv = str(gid).strip() == str(settings.main_guild_id or "1428666546942902294").strip()
                            saved_ical = academy_service.get_guild_saved_ical_url(gid)
                            if saved_ical or (is_main_srv and (settings.moodle_ical_url or (settings.moodle_username and settings.moodle_password))):
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                                try:
                                    await asyncio.to_thread(
                                        academy_service.sync_moodle_ics_content,
                                        gid,
                                        "",
                                        "Sync 00:01 WIB",
                                        saved_ical,
                                        "",
                                        "",
                                        "",
                                        False,
                                    )
                                except Exception:
                                    pass

                            unsent_tasks = academy_service.filter_unsent_daily_reminder_tasks(
                                guild_id=gid,
                                date_wib_str=today_wib,
                                now=now_utc,
                            )
                            if unsent_tasks:
                                channel = await self._resolve_discord_text_channel(g, ch_id)
                                if channel and hasattr(channel, "send"):
                                    daily_files, mod_metas = _collect_task_module_files(
                                        gid,
                                        task_ids=[t.task_id for t in unsent_tasks],
                                    )
                                    daily_emb = build_daily_task_reminder_embed(
                                        tasks=unsent_tasks,
                                        date_wib_str=today_wib,
                                        now_ref=now_utc,
                                        module_metas=mod_metas,
                                    )
                                    if daily_files:
                                        await channel.send(embed=daily_emb, files=daily_files)
                                    else:
                                        await channel.send(embed=daily_emb)
                                    academy_service.mark_daily_reminder_sent(
                                        guild_id=gid,
                                        task_ids=[t.task_id for t in unsent_tasks],
                                        channel_id=ch_id,
                                        date_wib_str=today_wib,
                                    )
                                    logger.info(
                                        "Berhasil mengirim Pengingat Tugas Harian 00:01 WIB (%d tugas) ke channel %s di Guild %s.",
                                        len(unsent_tasks),
                                        ch_id,
                                        gid,
                                    )

<<<<<<< HEAD
=======
                        # 2. Evaluasi Pengingat Bertahap (H-3d, H-6h, H-1h)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                        due_list = academy_service.evaluate_due_reminders(gid, now=now_utc)
                        if due_list:
                            channel = await self._resolve_discord_text_channel(g, ch_id)
                            if channel and hasattr(channel, "send"):
                                for item in due_list:
                                    dl_str, countdown_str = _format_wib_deadline_and_countdown(
                                        item["deadline_iso"], now_ref=now_utc
                                    )
                                    stage_files, stage_mod_metas = _collect_task_module_files(
                                        gid,
                                        task_ids=[item["task_id"]],
                                    )
                                    mod_note = ""
                                    if stage_mod_metas:
                                        mod_names = ", ".join(f"`{m['original_filename']}`" for m in stage_mod_metas[:5])
                                        mod_note = f"\n📎 **File Modul Terlampir:** {mod_names}"
                                    stage_emb = _make_embed(
                                        title=f"⏰ Pengingat Tenggat ({item['stage']}): {item['title']}",
                                        description=(
                                            f"📚 **Mata Kuliah:** {item['course_name']}\n"
                                            f"🗓️ **Tenggat Waktu:** `{dl_str}` ({countdown_str})\n"
                                            f"🆔 **ID Tugas:** `{item['task_id']}`"
                                            f"{mod_note}"
                                        ),
                                        color=0xF59E0B if item["stage"] != "H-1h" else 0xEF4444,
                                        category_label=f"Athenaa Deadline Alert • Tahap {item['stage']}",
                                    )
                                    if stage_files:
                                        await channel.send(embed=stage_emb, files=stage_files)
                                    else:
                                        await channel.send(embed=stage_emb)
                except Exception as exc:
                    logger.debug("Loop pengingat harian selesai dengan catatan: %s", exc)
                await asyncio.sleep(20.0)

<<<<<<< HEAD
        async def _ensure_bot_unmuted_in_vc(self, guild: Any, vc: Any) -> None:
            """Memastikan bot tidak dalam kondisi self_mute atau server mute saat berada di Voice Channel."""
            try:
                bot_member = getattr(guild, "me", None)
                if bot_member and getattr(bot_member, "voice", None):
                    vstate = bot_member.voice
                    self_mute = getattr(vstate, "self_mute", False)
                    server_mute = getattr(vstate, "mute", False)
                    if self_mute or server_mute:
                        logger.warning(
                            "Bot muted detected in guild %s: self_mute=%s, server_mute=%s, unmuting...",
                            guild.id, self_mute, server_mute
                        )
                    if self_mute and getattr(vc, "channel", None):
                        await guild.change_voice_state(channel=vc.channel, self_mute=False, self_deaf=True)
                    if server_mute:
                        try:
                            await bot_member.edit(mute=False)
                        except Exception:
                            pass
            except Exception:
                pass

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
        async def ensure_voice_connected(
            self,
            guild_id: str,
            preferred_channel_id: Optional[str] = None,
            requester_user_id: Optional[str] = None,
        ) -> Optional[discord.VoiceClient]:
            guild = self.get_guild(int(guild_id)) if guild_id and str(guild_id).isdigit() else None
            if not guild:
                logger.warning("Guild %s tidak ditemukan saat akan join voice.", guild_id)
                return None

            async with self._get_connect_lock(guild_id):
                st = queue_service.get_state(guild_id)
                vc: Optional[discord.VoiceClient] = guild.voice_client  # type: ignore

<<<<<<< HEAD
                # Cari Voice Channel tempat user yang me-request (requester_user_id) berada saat ini
                requester_vc: Optional[Any] = None
                req_uid_str = str(requester_user_id or "").strip()
                if req_uid_str.isdigit():
                    member = guild.get_member(int(req_uid_str))
                    if not member:
                        try:
                            member = await guild.fetch_member(int(req_uid_str))
                        except Exception:
                            member = None
                    if member and getattr(member, "voice", None) and getattr(member.voice, "channel", None):
                        requester_vc = member.voice.channel

                # 1. JIKA BOT SUDAH CONNECT DI VOICE:
                if vc is not None:
                    if vc.is_connected() and vc.channel:
                        # Jika ada requester spesifik dan dia tidak di voice channel sama sekali, tolak!
                        if req_uid_str.isdigit() and requester_vc is None:
                            logger.info(
                                "Menolak kontrol voice di Guild %s: User %s tidak berada di Voice Channel.",
                                guild.name,
                                req_uid_str,
                            )
                            return None
                        # Jika requester berada di channel berbeda dan channel bot saat ini sudah kosong (0 manusia lain), pindah ke channel requester
                        if requester_vc is not None and vc.channel.id != requester_vc.id:
                            other_humans = [
                                m for m in getattr(vc.channel, "members", [])
                                if not getattr(m, "bot", False) and str(getattr(m, "id", "")) != req_uid_str
                            ]
                            if other_humans:
                                logger.info(
                                    "Bot sedang aktif bersama anggota lain di '%s', menolak pindah ke '%s'.",
                                    vc.channel.name,
                                    requester_vc.name,
                                )
                                return None
                            try:
                                await vc.move_to(requester_vc)
                                st.voice_channel_id = str(requester_vc.id)
                                st.voice_channel_name = requester_vc.name
                            except Exception:
                                pass
                        else:
                            st.voice_channel_id = str(vc.channel.id)
                            st.voice_channel_name = vc.channel.name
                        await self._ensure_bot_unmuted_in_vc(guild, vc)
                        return vc

                    # Tunggu hingga 4 detik jika discord.py sedang auto-reconnect internal
                    for _ in range(16):
                        await asyncio.sleep(0.25)
                        vc_check: Optional[discord.VoiceClient] = guild.voice_client  # type: ignore
                        if vc_check and vc_check.is_connected() and vc_check.channel:
                            st.voice_channel_id = str(vc_check.channel.id)
                            st.voice_channel_name = vc_check.channel.name
                            await self._ensure_bot_unmuted_in_vc(guild, vc_check)
=======
                # 1. JIKA BOT SUDAH CONNECT DI VOICE:
                # Jangan pernah pindah channel sendiri (kecuali dipindah manual oleh user di Discord)!
                if vc is not None:
                    if vc.is_connected():
                        if vc.channel:
                            st.voice_channel_id = str(vc.channel.id)
                            st.voice_channel_name = vc.channel.name
                        return vc

                    # Tunggu hingga 5 detik jika discord.py sedang auto-reconnect internal (code 1006)
                    for _ in range(20):
                        await asyncio.sleep(0.25)
                        vc_check: Optional[discord.VoiceClient] = guild.voice_client  # type: ignore
                        if vc_check and vc_check.is_connected():
                            if vc_check.channel:
                                st.voice_channel_id = str(vc_check.channel.id)
                                st.voice_channel_name = vc_check.channel.name
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                            return vc_check

                    try:
                        await vc.disconnect(force=True)
<<<<<<< HEAD
                        await asyncio.sleep(0.5)
=======
                        await asyncio.sleep(0.6)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                    except Exception:
                        pass

                # 2. JIKA BOT BELUM CONNECT DI VOICE:
<<<<<<< HEAD
                # WAJIB mengikuti Voice Channel dari user yang login / me-request (requester_user_id)!
                # JANGAN PERNAH masuk ke Voice Channel milik user lain secara sembarangan!
                target_channel: Optional[Any] = requester_vc

                # Hanya jika dipicu oleh Autoplay internal dan preferred_channel_id memang masih berisi manusia
                if target_channel is None and req_uid_str == "autoplay" and preferred_channel_id and str(preferred_channel_id).isdigit():
                    ch = guild.get_channel(int(preferred_channel_id))
                    if ch is not None and any(not getattr(m, "bot", False) for m in getattr(ch, "members", [])):
                        target_channel = ch

                if not target_channel:
                    logger.info(
                        "Batal join voice di Guild %s: User (%s) belum bergabung ke Voice Channel mana pun.",
=======
                target_channel: Optional[discord.VoiceChannel] = None

                if requester_user_id and str(requester_user_id).isdigit():
                    member = guild.get_member(int(requester_user_id))
                    if not member:
                        try:
                            member = await guild.fetch_member(int(requester_user_id))
                        except Exception:
                            member = None
                    if member and member.voice and isinstance(member.voice.channel, discord.VoiceChannel):
                        target_channel = member.voice.channel

                # Fallback 1: gunakan preferred_channel_id jika ada member manusia di dalamnya atau mode 24/7 / web control
                if not target_channel and preferred_channel_id and str(preferred_channel_id).isdigit():
                    ch = guild.get_channel(int(preferred_channel_id))
                    if isinstance(ch, discord.VoiceChannel):
                        if st.mode_247 or any(not getattr(m, "bot", False) for m in ch.members) or not str(requester_user_id or "").isdigit():
                            target_channel = ch

                # Fallback 2: cari voice channel mana pun di guild yang sedang berisi member manusia
                if not target_channel:
                    for ch in getattr(guild, "voice_channels", []) or []:
                        if any(not getattr(m, "bot", False) for m in getattr(ch, "members", [])):
                            target_channel = ch
                            break

                # Fallback 3: jika mode 24/7 aktif, masuk ke voice channel pertama yang tersedia di guild
                if not target_channel and st.mode_247:
                    vcs = getattr(guild, "voice_channels", []) or []
                    if vcs:
                        target_channel = vcs[0]

                if not target_channel:
                    logger.info(
                        "Batal join voice di Guild %s: Tidak ditemukan Voice Channel aktif untuk requester (%s).",
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                        guild.name,
                        requester_user_id,
                    )
                    return None

                st.voice_channel_id = str(target_channel.id)
                st.voice_channel_name = target_channel.name

                try:
<<<<<<< HEAD
                    vc = await target_channel.connect(timeout=15.0, reconnect=True, self_deaf=True, self_mute=False)
                    await self._ensure_bot_unmuted_in_vc(guild, vc)
                    logger.info(
                        "Berhasil bergabung ke Voice Channel '%s' (ID: %s) mengikuti user %s di server %s.",
                        target_channel.name,
                        target_channel.id,
                        requester_user_id,
=======
                    vc = await target_channel.connect(timeout=15.0, reconnect=True, self_deaf=True)
                    logger.info(
                        "Berhasil bergabung ke Voice Channel '%s' (ID: %s) di server %s.",
                        target_channel.name,
                        target_channel.id,
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                        guild.name,
                    )
                    return vc
                except discord.ClientException:
                    vc_now: Optional[discord.VoiceClient] = guild.voice_client  # type: ignore
                    if vc_now and vc_now.is_connected():
<<<<<<< HEAD
                        await self._ensure_bot_unmuted_in_vc(guild, vc_now)
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                        return vc_now
                    return None
                except Exception as exc:
                    logger.error(
                        "Gagal menghubungkan ke Voice Channel '%s' (ID: %s): %s",
                        target_channel.name,
                        target_channel.id,
                        exc,
                    )
                    return None

        async def start_or_sync_voice_playback(
            self,
            guild_id: str,
            requester_user_id: Optional[str] = None,
            seek_seconds: int = 0,
            force_restart: bool = False,
        ) -> bool:
            st = queue_service.get_state(guild_id)
            track = st.current_track
            if not track or (not st.is_playing and not st.is_paused):
                return False

<<<<<<< HEAD
            _ensure_opus_loaded()

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
            target_item_id = track.item_id
            sync_key = f"{target_item_id}:{int(seek_seconds)}"

            guild_obj = self.get_guild(int(guild_id)) if guild_id.isdigit() else None
            vc_existing: Optional[discord.VoiceClient] = guild_obj.voice_client if guild_obj else None  # type: ignore

            if not force_restart and self._syncing_track_key.get(guild_id) == sync_key:
                return True

            if not force_restart:
                if (
                    seek_seconds == 0
                    and self._active_vc_track_id.get(guild_id) == target_item_id
                    and vc_existing
                    and vc_existing.is_connected()
                    and (vc_existing.is_playing() or vc_existing.is_paused())
                ):
                    if vc_existing.source and hasattr(vc_existing.source, "volume"):
                        try:
<<<<<<< HEAD
                            vc_existing.source.volume = max(0.05, min(2.0, st.volume / 100.0))
=======
                            vc_existing.source.volume = max(0.01, min(2.0, st.volume / 100.0))
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                            self._active_vc_volume[guild_id] = st.volume
                        except Exception:
                            pass
                    return True

            self._syncing_track_key[guild_id] = sync_key
            self._last_sync_attempt[guild_id] = time.monotonic()
            self._track_stopped_mono.pop(guild_id, None)
            self._playback_gen[guild_id] = self._playback_gen.get(guild_id, 0) + 1
            my_gen = self._playback_gen[guild_id]
            st.is_loading_stream = True

            if vc_existing and (vc_existing.is_playing() or vc_existing.is_paused()):
                if self._active_vc_track_id.get(guild_id) != target_item_id or force_restart or seek_seconds > 0:
                    self._active_vc_track_id.pop(guild_id, None)
                    vc_existing.stop()

            await self._notify_web(guild_id)

            try:
<<<<<<< HEAD
                use_local_file_fallback = bool(getattr(track, "_use_local_file_fallback", False))

                if force_restart and seek_seconds == 0 and track.source_type != "radio":
                    if track.source_url:
                        invalidate_stream_cache(track.source_url)
                    if not use_local_file_fallback:
                        track.stream_url = ""

                stream_url = track.stream_url if not _needs_stream_extraction(track.stream_url) else ""

                # Jika retry karena HTTP stream terputus/diblokir, unduh ke file lokal via yt-dlp agar FFmpeg membaca dari disk
                if use_local_file_fallback and not (stream_url.startswith("/") and Path(stream_url).is_file()):
                    target_query = _build_track_stream_query(track)
                    dl_info = await asyncio.to_thread(download_playable_audio_file_ytdlp, target_query, guild_id)
                    if dl_info and dl_info.get("local_path"):
                        stream_url = str(dl_info["local_path"])
                        track.stream_url = stream_url

=======
                if force_restart and seek_seconds == 0 and track.source_type != "radio":
                    if track.source_url:
                        invalidate_stream_cache(track.source_url)
                    track.stream_url = ""

                stream_url = track.stream_url if not _needs_stream_extraction(track.stream_url) else ""
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                if not stream_url:
                    target_query = _build_track_stream_query(track)
                    info = await asyncio.to_thread(extract_playable_stream_ytdlp, target_query)
                    if info and info.get("stream_url") and not _needs_stream_extraction(str(info["stream_url"])):
                        stream_url = str(info["stream_url"])
                        track.stream_url = stream_url
                        if info.get("user_agent"):
                            self._track_user_agents[track.item_id] = str(info["user_agent"])
<<<<<<< HEAD
                        # Store cookies for HLS streams (needed for segment requests)
                        if info.get("cookies"):
                            track._stream_cookies = str(info["cookies"])
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                        if info.get("duration_sec") and int(info["duration_sec"]) > 0:
                            track.duration_sec = int(info["duration_sec"])
                        if info.get("thumbnail_url") and not track.thumbnail_url:
                            track.thumbnail_url = str(info["thumbnail_url"])

                if not stream_url and self._playback_gen.get(guild_id) == my_gen:
                    yt_alt = await asyncio.to_thread(
                        _fetch_youtube_alt_stream_fallback, track.title, track.artist
                    )
                    if yt_alt and yt_alt.get("stream_url"):
                        stream_url = str(yt_alt["stream_url"])
                        track.stream_url = stream_url
                        if yt_alt.get("duration_sec") and int(yt_alt["duration_sec"]) > 0:
                            track.duration_sec = int(yt_alt["duration_sec"])
                        if yt_alt.get("thumbnail_url") and not track.thumbnail_url:
                            track.thumbnail_url = str(yt_alt["thumbnail_url"])
<<<<<<< HEAD
                        if yt_alt.get("cookies"):
                            track._stream_cookies = str(yt_alt["cookies"])

                if not stream_url and self._playback_gen.get(guild_id) == my_gen and track.source_type != "radio":
                    target_query = _build_track_stream_query(track)
                    dl_info = await asyncio.to_thread(download_playable_audio_file_ytdlp, target_query, guild_id)
                    if dl_info and dl_info.get("local_path"):
                        stream_url = str(dl_info["local_path"])
                        track.stream_url = stream_url
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

                if (
                    self._playback_gen.get(guild_id) != my_gen
                    or not st.current_track
                    or st.current_track.item_id != target_item_id
                    or (not st.is_playing and not st.is_paused)
                ):
                    return False

                if not stream_url:
                    logger.warning("Stream tidak ditemukan untuk lagu '%s', melewati ke lagu berikutnya.", track.title)
                    asyncio.create_task(self._handle_track_finished(guild_id, my_gen))
                    return False

                async with self._get_lock(guild_id):
                    if (
                        self._playback_gen.get(guild_id) != my_gen
                        or not st.current_track
                        or st.current_track.item_id != target_item_id
                        or (not st.is_playing and not st.is_paused)
                    ):
                        return False

                    req_uid = requester_user_id or track.requester_id or st.host_user_id
                    vc = await self.ensure_voice_connected(guild_id, st.voice_channel_id, req_uid)
                    if not vc:
                        return False

<<<<<<< HEAD
                    # Ensure bot is not muted (self_mute or server mute) before playing
                    await self._ensure_bot_unmuted_in_vc(guild_obj, vc)

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                    ffmpeg_bin = shutil.which("ffmpeg")
                    if not ffmpeg_bin:
                        logger.error("Binary ffmpeg tidak ditemukan di PATH kontainer!")
                        return False

<<<<<<< HEAD
                    is_local_file = stream_url.startswith("/") and Path(stream_url).is_file()
                    if is_local_file:
                        before_opts = "-nostdin"
                    else:
                        ua_val = (
                            self._track_user_agents.get(track.item_id)
                            or DEFAULT_STREAM_USER_AGENT
                        )
                        # Extract cookies for HLS streams (stored when stream was extracted)
                        cookie_val = getattr(track, "_stream_cookies", "") or ""
                        # FFmpeg parses before_options with its own escaping (not shlex).
                        # Do NOT use shlex.quote() - it adds literal quotes that break YouTube auth.
                        # Use double-quotes for values containing spaces, and escape embedded quotes/backslashes.
                        def _ffmpeg_escape(val: str) -> str:
                            """Escape value for ffmpeg before_options: wrap in double quotes, escape internal quotes/backslashes."""
                            return '"' + val.replace('\\', '\\\\').replace('"', '\\"') + '"'

                        before_opts = f'-user_agent {_ffmpeg_escape(ua_val)} '
                        if cookie_val:
                            # Use -cookies option (correct ffmpeg option for HTTP cookies) instead of -headers
                            # -headers with CRLF breaks shlex.split() parsing in discord.py
                            # -cookies expects format: "name1=value1; name2=value2; ..."
                            before_opts += f'-cookies {_ffmpeg_escape(cookie_val)} '
                            logger.debug("HLS Cookie added for guild %s: %s", guild_id, cookie_val[:50] + "..." if len(cookie_val) > 50 else cookie_val)
                        before_opts += (
                            "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin"
                        )
                        logger.debug("FFmpeg before_options for guild %s: %s", guild_id, before_opts[:200])
                    if seek_seconds > 0 and track.source_type != "radio":
                        before_opts = f"-ss {int(seek_seconds)} {before_opts}"

                    vol_float = max(0.05, min(2.0, (st.volume or 80) / 100.0))

                    # Debug: Log voice client state before playing
                    logger.info(
                        "VoiceClient state for guild %s: connected=%s, channel=%s, ws_state=%s",
                        guild_id,
                        vc.is_connected(),
                        getattr(vc.channel, "name", "None") if vc.channel else "None",
                        getattr(vc, "_ws", "Unknown")
                    )
                    # Debug: Log bot voice state
                    bot_member = getattr(guild_obj, "me", None)
                    if bot_member and getattr(bot_member, "voice", None):
                        vstate = bot_member.voice
                        logger.info(
                            "Bot voice state: self_mute=%s, mute=%s, self_deaf=%s, deaf=%s, channel=%s",
                            getattr(vstate, "self_mute", None),
                            getattr(vstate, "mute", None),
                            getattr(vstate, "self_deaf", None),
                            getattr(vstate, "deaf", None),
                            getattr(vstate.channel, "name", "None") if getattr(vstate, "channel", None) else "None"
                        )
=======
                    ua_val = (
                        self._track_user_agents.get(track.item_id)
                        or DEFAULT_STREAM_USER_AGENT
                    ).replace('"', "")
                    before_opts = (
                        f'-user_agent "{ua_val}" '
                        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin"
                    )
                    if seek_seconds > 0 and track.source_type != "radio":
                        before_opts = f"-ss {int(seek_seconds)} {before_opts}"

                    vol_float = max(0.01, min(2.0, st.volume / 100.0))
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

                    if vc.is_playing() or vc.is_paused():
                        vc.stop()

                    play_start_mono = time.monotonic()

                    def _after_track(err: Optional[Exception]) -> None:
                        if err:
                            logger.warning("FFmpeg playback error di guild %s: %s", guild_id, err)
                            if track.source_url:
                                invalidate_stream_cache(track.source_url)
                        if self._playback_gen.get(guild_id) != my_gen:
                            return
                        elapsed_play = time.monotonic() - play_start_mono
<<<<<<< HEAD
                        # Jika stream HTTP terputus mendadak (<3.0 detik sejak mulai),
                        # otomatis unduh file audio lokal via yt-dlp agar pemutaran dijamin mengeluarkan suara!
                        if (
                            elapsed_play < 3.0
=======
                        # Jika stream putus mendadak (<2.5 detik sejak mulai) dan bukan karena seek di ujung lagu,
                        # re-extract stream URL segar sekali lagi agar lagu tidak ter-skip sia-sia.
                        if (
                            elapsed_play < 2.5
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                            and seek_seconds == 0
                            and track.source_type != "radio"
                            and not getattr(track, "_retried_fresh_stream", False)
                        ):
                            setattr(track, "_retried_fresh_stream", True)
<<<<<<< HEAD
                            setattr(track, "_use_local_file_fallback", True)
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                            if track.source_url:
                                invalidate_stream_cache(track.source_url)
                            track.stream_url = ""
                            if self.loop and self.loop.is_running():
                                asyncio.run_coroutine_threadsafe(
                                    self.start_or_sync_voice_playback(
                                        guild_id,
                                        track.requester_id,
                                        seek_seconds=0,
                                        force_restart=True,
                                    ),
                                    self.loop,
                                )
                            return
                        if self.loop and self.loop.is_running():
                            asyncio.run_coroutine_threadsafe(
                                self._handle_track_finished(guild_id, my_gen), self.loop
                            )

<<<<<<< HEAD
                    opus_ready = _ensure_opus_loaded()
                    played_ok = False
                    # Debug: Log stream URL type and ffmpeg command being constructed
                    stream_type = "local" if is_local_file else ("HLS/m3u8" if ".m3u8" in stream_url else "direct")
                    logger.info(
                        "Starting playback for guild %s: track=%s, stream_type=%s, url_prefix=%s",
                        guild_id, track.title, stream_type, stream_url[:80]
                    )
                    logger.debug("Full ffmpeg before_options: %s", before_opts)
                    if opus_ready:
                        try:
                            pcm_audio = discord.FFmpegPCMAudio(
                                stream_url,
                                executable=ffmpeg_bin,
                                before_options=before_opts,
                                options="-vn",
                            )
                            audio_source: Any = discord.PCMVolumeTransformer(pcm_audio, volume=vol_float)
                            vc.play(audio_source, after=_after_track)
                            # Verify playback actually started
                            await asyncio.sleep(0.5)
                            if vc.is_playing():
                                logger.info("Playback confirmed: vc.is_playing()=True for guild %s", guild_id)
                                played_ok = True
                            else:
                                logger.error("Playback FAILED: vc.is_playing()=False immediately after play() for guild %s", guild_id)
                                played_ok = False
                        except Exception as pcm_exc:
                            logger.warning("FFmpegPCMAudio gagal (%s), beralih ke FFmpegOpusAudio...", pcm_exc)

                    if not played_ok:
                        af_chain = f"volume={vol_float:.2f}"
=======
                    try:
                        pcm_audio = discord.FFmpegPCMAudio(
                            stream_url,
                            executable=ffmpeg_bin,
                            before_options=before_opts,
                            options="-vn -af aresample=async=1:first_pts=0",
                        )
                        audio_source: Any = discord.PCMVolumeTransformer(pcm_audio, volume=vol_float)
                    except Exception:
                        af_chain = f"volume={vol_float:.2f},aresample=async=1:first_pts=0"
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                        audio_source = discord.FFmpegOpusAudio(
                            stream_url,
                            bitrate=128,
                            executable=ffmpeg_bin,
                            before_options=before_opts,
                            options=f'-vn -filter:a "{af_chain}"',
                        )
<<<<<<< HEAD
                        vc.play(audio_source, after=_after_track)
                        # Verify fallback playback
                        await asyncio.sleep(0.5)
                        if vc.is_playing():
                            logger.info("Fallback playback confirmed: vc.is_playing()=True for guild %s", guild_id)
                        else:
                            logger.error("Fallback playback FAILED: vc.is_playing()=False for guild %s", guild_id)

=======

                    vc.play(audio_source, after=_after_track)
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                    if st.is_paused:
                        vc.pause()

                    self._active_vc_track_id[guild_id] = track.item_id
                    self._active_vc_volume[guild_id] = st.volume
                    self._last_sync_attempt[guild_id] = time.monotonic()
                    self._track_started_mono[guild_id] = time.monotonic() - float(seek_seconds)
                    self._track_pause_mono.pop(guild_id, None)
                    self._track_stopped_mono.pop(guild_id, None)
                    st.position_sec = int(seek_seconds)
                    st.is_loading_stream = False
                    await self._notify_web(guild_id)
                    self._schedule_prefetch(guild_id)
                    logger.info(
<<<<<<< HEAD
                        "Memutar audio '%s — %s' di Voice Channel '%s' (vol=%d%%, mode=%s).",
=======
                        "Memutar audio '%s — %s' di Voice Channel '%s' (vol=%d%%).",
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                        track.title,
                        track.artist,
                        st.voice_channel_name,
                        st.volume,
<<<<<<< HEAD
                        "local-file" if is_local_file else ("pcm-opus" if opus_ready else "ffmpeg-opus"),
=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
                    )
                    return True
            except Exception as exc:
                logger.error("Gagal memutar audio di Discord Voice: %s", exc)
                return False
            finally:
                if self._syncing_track_key.get(guild_id) == sync_key:
                    self._syncing_track_key.pop(guild_id, None)
                if self._playback_gen.get(guild_id) == my_gen:
                    st.is_loading_stream = False

        async def _handle_track_finished(self, guild_id: str, gen_id: Optional[int] = None) -> None:
            if gen_id is not None and self._playback_gen.get(guild_id) != gen_id:
                return
            vc_guild = self.get_guild(int(guild_id)) if guild_id.isdigit() else None
            vc: Optional[discord.VoiceClient] = vc_guild.voice_client if vc_guild else None  # type: ignore
            if gen_id is None and vc and (vc.is_playing() or vc.is_paused()):
                return

            self._active_vc_track_id.pop(guild_id, None)
            self._syncing_track_key.pop(guild_id, None)
            self._track_stopped_mono.pop(guild_id, None)
            self._last_sync_attempt[guild_id] = time.monotonic()

            st = queue_service.get_state(guild_id)
            if (
                st.autoplay
                and not st.queue
                and st.loop_mode != "one"
                and not queue_service.prefetched_autoplay.get(guild_id)
            ):
                seed_tr = st.current_track or st.last_played_track
                if seed_tr is not None:
                    try:
                        dyn_cands = await asyncio.to_thread(
                            queue_service._build_default_autoplay_candidates,
                            guild_id,
                            seed_tr,
                            True,
                        )
                        if dyn_cands:
                            queue_service.set_prefetched_autoplay(guild_id, dyn_cands)
                    except Exception:
                        pass

            next_item = queue_service.advance_track(guild_id)
            if next_item:
                if getattr(next_item, "is_autoplay", False):
                    logger.info(
                        "Autoplay memutar lagu lanjutan '%s — %s' di Guild %s.",
                        next_item.title,
                        next_item.artist,
                        guild_id,
                    )
            else:
                await self._notify_web(guild_id)

        async def apply_web_control(self, guild_id: str, action: str, value: Any = None) -> None:
            guild = self.get_guild(int(guild_id)) if guild_id.isdigit() else None
            st = queue_service.get_state(guild_id)
            vc: Optional[discord.VoiceClient] = guild.voice_client if guild else None  # type: ignore

            if action == "pause":
                self._track_pause_mono[guild_id] = time.monotonic()
                if vc and vc.is_playing():
                    vc.pause()
            elif action == "resume":
                p_mono = self._track_pause_mono.pop(guild_id, None)
                if p_mono is not None and guild_id in self._track_started_mono:
                    self._track_started_mono[guild_id] += (time.monotonic() - p_mono)
                if vc and vc.is_paused():
                    vc.resume()
                elif st.current_track:
                    await self.start_or_sync_voice_playback(guild_id, seek_seconds=st.position_sec)
            elif action == "stop":
                self._playback_gen[guild_id] = self._playback_gen.get(guild_id, 0) + 1
                self._active_vc_track_id.pop(guild_id, None)
                self._active_vc_volume.pop(guild_id, None)
                self._syncing_track_key.pop(guild_id, None)
                self._track_stopped_mono.pop(guild_id, None)
                st.is_loading_stream = False
                if vc:
                    if vc.is_playing() or vc.is_paused():
                        vc.stop()
                    if not st.mode_247 and vc.is_connected():
                        await vc.disconnect(force=True)
            elif action == "skip":
                if st.current_track:
                    await self.start_or_sync_voice_playback(guild_id, st.current_track.requester_id)
                elif vc and (vc.is_playing() or vc.is_paused()):
                    self._playback_gen[guild_id] = self._playback_gen.get(guild_id, 0) + 1
                    self._active_vc_track_id.pop(guild_id, None)
                    vc.stop()
            elif action == "volume":
                if vc and vc.source and hasattr(vc.source, "volume"):
                    try:
                        vc.source.volume = max(0.01, min(2.0, st.volume / 100.0))
                        self._active_vc_volume[guild_id] = st.volume
                        await self._notify_web(guild_id)
                        return
                    except Exception:
                        pass
                if st.current_track and vc and (vc.is_playing() or vc.is_paused()):
                    await self.start_or_sync_voice_playback(
                        guild_id,
                        st.current_track.requester_id,
                        seek_seconds=st.position_sec,
                        force_restart=True,
                    )
            elif action == "seek" and st.current_track:
                await self.start_or_sync_voice_playback(
                    guild_id,
                    st.current_track.requester_id,
                    seek_seconds=st.position_sec,
                    force_restart=True,
                )
            elif action == "autoplay":
                if st.autoplay:
                    self._schedule_prefetch(guild_id)
                    if st.current_track and (not vc or not vc.is_connected() or (not vc.is_playing() and not vc.is_paused())):
                        await self.start_or_sync_voice_playback(guild_id, st.current_track.requester_id)
            elif action == "mode_247":
                if st.mode_247 and guild:
                    await self.ensure_voice_connected(guild_id, st.voice_channel_id, st.host_user_id)
                elif not st.mode_247 and not st.current_track and vc and vc.is_connected():
                    human_in_vc = any(not getattr(m, "bot", False) for m in getattr(vc.channel, "members", []))
                    if not human_in_vc:
                        await vc.disconnect(force=True)
            await self._notify_web(guild_id)

        async def on_message(self, message: discord.Message) -> None:
            if message.author.bot or not message.guild:
                return

            guild_id = str(message.guild.id)
            user_id = str(message.author.id)

            try:
                if leveling_service.clear_afk(guild_id, user_id):
                    afk_back_emb = _make_embed(
                        title="👋 Selamat Datang Kembali!",
                        description=f"Status AFK untuk {message.author.mention} telah dicabut secara otomatis.",
                        color=0xDC95FF,
                        category_label="Sistem Status AFK",
                    )
                    await message.channel.send(embed=afk_back_emb, delete_after=8)
            except Exception:
                pass

            for mentioned in message.mentions:
                afk_info: Optional[Dict[str, Any]] = None
                try:
                    if hasattr(leveling_service, "get_afk"):
                        afk_info = leveling_service.get_afk(guild_id, str(mentioned.id))
                    else:
                        afk_list = leveling_service.list_afk(guild_id)
                        afk_info = next(
                            (a for a in afk_list if str(a.get("user_id")) == str(mentioned.id)),
                            None,
                        )
                except Exception:
                    try:
                        afk_list = leveling_service.list_afk(guild_id)
                        afk_info = next(
                            (a for a in afk_list if str(a.get("user_id")) == str(mentioned.id)),
                            None,
                        )
                    except Exception:
                        afk_info = None

                if afk_info:
                    afk_emb = _make_embed(
                        title=f"💤 {mentioned.display_name} Sedang AFK",
                        description=(
                            f"💬 **Alasan:** {afk_info.get('reason', 'Sedang AFK')}\n"
                            f"🕒 **Sejak:** `{str(afk_info.get('started_at', ''))[:19].replace('T', ' ')} UTC`"
                        ),
                        color=0xF59E0B,
                        category_label="Status AFK Anggota",
                        thumbnail_url=mentioned.display_avatar.url if mentioned.display_avatar else "",
                    )
                    await message.channel.send(embed=afk_emb)

            leveled_up, new_level, curr_exp, max_exp = leveling_service.process_message_activity(
                guild_id=guild_id,
                user_id=user_id,
                username=message.author.name,
                display_name=message.author.display_name,
                message_content=message.content,
                is_bot=message.author.bot,
            )
            if leveled_up:
                lvl_emb = _make_embed(
                    title="🎉 LEVEL UP! Naik Peringkat Server",
                    description=(
                        f"Selamat {message.author.mention}, kamu naik ke **Level {new_level}**!\n\n"
                        f"📊 **Progres EXP:** {_build_progress_bar(curr_exp, max_exp)}\n"
                        f"✨ **Detail EXP:** `{curr_exp} / {max_exp} EXP`"
                    ),
                    color=0x8B5CF6,
                    category_label="Athenaa Leaderboard & Leveling",
                    thumbnail_url=message.author.display_avatar.url if message.author.display_avatar else "",
                )
                await message.channel.send(embed=lvl_emb)

            await self.process_commands(message)

        async def on_voice_state_update(
            self,
            member: discord.Member,
            before: discord.VoiceState,
            after: discord.VoiceState,
        ) -> None:
            guild_id = str(member.guild.id)
            st = queue_service.get_state(guild_id)

            # 1. Jika yang berpindah/di-move manual oleh admin adalah BOT ITU SENDIRI:
            if self.user and member.id == self.user.id:
                if after.channel is not None:
                    st.voice_channel_id = str(after.channel.id)
                    st.voice_channel_name = after.channel.name
                    logger.info(
                        "Bot dipindahkan secara manual ke Voice Channel '%s' (ID: %s).",
                        after.channel.name,
                        after.channel.id,
                    )
                else:
                    # Bot di-disconnect manual dari Discord
                    self._playback_gen[guild_id] = self._playback_gen.get(guild_id, 0) + 1
                    self._active_vc_track_id.pop(guild_id, None)
                    self._syncing_track_key.pop(guild_id, None)
                await self._notify_web(guild_id)
                return

            # 2. Award EXP untuk aktivitas Voice member manusia (Join, Speak, Stream)
            if not member.bot:
                if before.channel is None and after.channel is not None:
                    leveling_service.process_voice_activity(
                        guild_id=guild_id,
                        user_id=str(member.id),
                        username=member.name,
                        display_name=member.display_name,
                        activity_type="voice_join",
                        cooldown_seconds=60,
                        exp_gain=20,
                    )
                elif (not before.self_stream and after.self_stream) or (not before.self_video and after.self_video):
                    leveling_service.process_voice_activity(
                        guild_id=guild_id,
                        user_id=str(member.id),
                        username=member.name,
                        display_name=member.display_name,
                        activity_type="voice_stream",
                        cooldown_seconds=60,
                        exp_gain=25,
                    )
                elif before.self_mute and not after.self_mute and after.channel is not None:
                    leveling_service.process_voice_activity(
                        guild_id=guild_id,
                        user_id=str(member.id),
                        username=member.name,
                        display_name=member.display_name,
                        activity_type="voice_speak",
                        cooldown_seconds=45,
                        exp_gain=15,
                    )

            # 3. Tangani transfer Host & auto-stop jika member keluar dari channel tempat bot berada
            if before.channel and (after.channel is None or after.channel.id != before.channel.id):
                active_members = [
                    {"id": str(m.id), "name": m.display_name}
                    for m in before.channel.members
                    if not m.bot
                ]
                queue_service.handle_host_left_voice(guild_id, str(member.id), active_members)

                # Jika bot sedang ada di channel tersebut dan semua manusia sudah keluar (dan bukan mode 24/7)
                vc: Optional[discord.VoiceClient] = member.guild.voice_client  # type: ignore
                if vc and vc.is_connected() and vc.channel and vc.channel.id == before.channel.id:
                    if not active_members and not st.mode_247:
                        queue_service.control_playback(
                            guild_id=guild_id,
                            action="stop",
                            actor_id="system",
                            is_admin=True,
                            is_owner=False,
                        )
                        await self.apply_web_control(guild_id, "stop")

                await self._notify_web(guild_id)

    bot = AthenaaDiscordBot()

    def _member_context(interaction: discord.Interaction):
        user = interaction.user
        is_admin = False
        roles: List[str] = []
        if isinstance(user, discord.Member):
            is_admin = bool(
                user.guild_permissions.administrator
                or getattr(user.guild_permissions, "manage_guild", False)
                or (interaction.guild and interaction.guild.owner_id == user.id)
            )
            roles = [str(r.id) for r in user.roles]
            for r in user.roles:
                rname = str(getattr(r, "name", "") or "").strip().lower()
                if rname in ("dj", "athenaa dj", "role dj", "music dj"):
                    roles.append("role-dj")
                    guild_id_str = str(interaction.guild_id or settings.main_guild_id)
                    cfg_dj = bot._get_guild_dj_role_id(guild_id_str)
                    if cfg_dj and cfg_dj not in roles:
                        roles.append(cfg_dj)
        return str(user.id), user.display_name, roles, is_admin, False

    def _has_guild_dj_role(guild_id: str, roles: List[str]) -> Tuple[str, bool]:
        dj_role_id = bot._get_guild_dj_role_id(guild_id)
        has_dj = (dj_role_id in roles) or ("role-dj" in roles)
        return dj_role_id, has_dj

    # =========================================================================
    # Modern Interactive Music Player Embed & Control View
    # =========================================================================
    def _build_now_playing_embed(guild_id: str) -> discord.Embed:
        st = queue_service.get_state(guild_id)
        if not st.current_track:
            return _make_embed(
                title="⏹️ Tidak Ada Lagu yang Sedang Diputar",
                description="Gunakan `/play <judul lagu>` atau cari dari Web Player untuk memulai sesi musik di Voice Channel.",
                color=0x64748B,
                category_label="Athenaa Music Player",
            )

        tr = st.current_track
        prog = _build_progress_bar(st.position_sec, tr.duration_sec, length=14)
        status_icon = "⏸️ Dijeda:" if st.is_paused else "▶️ Sedang Diputar:"
        transport_icon = "⏸️" if st.is_paused else "▶️"
        emb = _make_embed(
            title=f"{status_icon} {tr.title}",
            description=(
                f"🎤 **Penyanyi:** {tr.artist}\n"
                f"💿 **Album:** {tr.album or 'Single'}\n\n"
                f"{transport_icon} {prog}\n"
                f"⏱️ `{_format_mmss(st.position_sec)} / {_format_mmss(tr.duration_sec)}`"
            ),
            color=0xF59E0B if st.is_paused else 0xDC95FF,
            category_label=f"Voice Channel • {st.voice_channel_name or 'Active Voice'}",
            thumbnail_url=tr.thumbnail_url,
            footer_text="Athenaa Music Controller • Gunakan tombol di bawah atau Web Player",
        )
        emb.add_field(
            name="Diminta Oleh",
            value=f"👤 **{tr.requester_name or 'Member'}**",
            inline=True,
        )
        emb.add_field(
            name="Sumber Audio",
            value=_source_badge(tr.source_type),
            inline=True,
        )
        emb.add_field(
            name="Volume & Mode",
            value=f"🔊 `{st.volume}%` • Loop `{st.loop_mode.upper()}` • Auto `{'ON' if st.autoplay else 'OFF'}` • 24/7 `{'ON' if st.mode_247 else 'OFF'}`",
            inline=True,
        )

        if st.queue:
            nxt = st.queue[0]
            extra_count = f" *(+{len(st.queue) - 1} lagu lainnya)*" if len(st.queue) > 1 else ""
            next_val = f"⏭️ **{nxt.title}** — *{nxt.artist}* (`{_format_mmss(nxt.duration_sec)}`){extra_count}"
        else:
            next_val = "📻 *Autoplay Rekomendasi Aktif*" if st.autoplay else "📭 *Tidak ada lagu berikutnya di antrean*"
        emb.add_field(name="Lagu Berikutnya", value=next_val, inline=False)

        links_parts: List[str] = []
        if tr.source_url and tr.source_url.startswith(("http://", "https://")):
            links_parts.append(f"[🔗 Buka Sumber Audio]({tr.source_url})")
        if settings.web_base_url:
            links_parts.append(f"[🌐 Buka Web Dashboard]({settings.web_base_url})")
        if links_parts:
            emb.add_field(name="Tautan & Kontrol Web", value=" • ".join(links_parts), inline=False)

        return emb

    class MusicPlayerControlView(discord.ui.View):
        def __init__(self, guild_id: str):
            super().__init__(timeout=None)
            self.guild_id = guild_id

            controls = [
                ("⏯️ Jeda / Lanjut", discord.ButtonStyle.success, 0, self._on_toggle_pause),
                ("⏭️ Skip", discord.ButtonStyle.primary, 0, self._on_skip),
                ("⏹️ Stop", discord.ButtonStyle.danger, 0, self._on_stop),
                ("🔁 Loop", discord.ButtonStyle.secondary, 0, self._on_loop),
                ("🔀 Shuffle", discord.ButtonStyle.secondary, 0, self._on_shuffle),
                ("🔉 Vol -10%", discord.ButtonStyle.secondary, 1, self._on_vol_down),
                ("🔊 Vol +10%", discord.ButtonStyle.secondary, 1, self._on_vol_up),
                ("📻 Autoplay", discord.ButtonStyle.secondary, 1, self._on_autoplay),
                ("🌙 24/7", discord.ButtonStyle.secondary, 1, self._on_mode_247),
                ("🔄 Refresh", discord.ButtonStyle.secondary, 1, self._on_refresh),
                ("🎤 Lirik", discord.ButtonStyle.secondary, 2, self._on_lyrics),
                ("📋 Antrean", discord.ButtonStyle.secondary, 2, self._on_queue),
            ]
            for label, style, row, handler in controls:
                btn = discord.ui.Button(label=label, style=style, row=row)
                btn.callback = handler
                self.add_item(btn)

        async def _send_denied(self, interaction: discord.Interaction, message: str) -> None:
            emb = _make_embed(title="🔒 Akses Ditolak", description=message, color=0xEF4444)
            if interaction.response.is_done():
                await interaction.followup.send(embed=emb, ephemeral=True)
            else:
                await interaction.response.send_message(embed=emb, ephemeral=True)

        async def _on_toggle_pause(self, interaction: discord.Interaction) -> None:
            st = queue_service.get_state(self.guild_id)
            if not st.current_track:
                await interaction.response.send_message("⏹️ Tidak ada lagu yang sedang diputar.", ephemeral=True)
                return
            action = "resume" if st.is_paused else "pause"
            uid, _, roles, is_admin, is_owner = _member_context(interaction)
            dj_role_id, has_dj = _has_guild_dj_role(self.guild_id, roles)
            try:
                queue_service.control_playback(
                    guild_id=self.guild_id,
                    action=action,
                    actor_id=uid,
                    user_roles=roles,
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=dj_role_id,
                    has_dj_role=has_dj,
                )
                asyncio.create_task(bot.apply_web_control(self.guild_id, action))
                await interaction.response.edit_message(
                    embed=_build_now_playing_embed(self.guild_id),
                    view=self,
                )
            except (PermissionError, ValueError, KeyError) as exc:
                await self._send_denied(interaction, str(exc))

        async def _on_skip(self, interaction: discord.Interaction) -> None:
            st = queue_service.get_state(self.guild_id)
            if not st.current_track and not st.queue:
                await interaction.response.send_message("📭 Antrean musik sedang kosong.", ephemeral=True)
                return
            uid, _, roles, is_admin, is_owner = _member_context(interaction)
            dj_role_id, has_dj = _has_guild_dj_role(self.guild_id, roles)
            try:
                queue_service.control_playback(
                    guild_id=self.guild_id,
                    action="skip",
                    actor_id=uid,
                    user_roles=roles,
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=dj_role_id,
                    has_dj_role=has_dj,
                )
                asyncio.create_task(bot.apply_web_control(self.guild_id, "skip"))
                await interaction.response.edit_message(
                    embed=_build_now_playing_embed(self.guild_id),
                    view=self,
                )
            except (PermissionError, ValueError, KeyError) as exc:
                await self._send_denied(interaction, str(exc))

        async def _on_stop(self, interaction: discord.Interaction) -> None:
            uid, _, roles, is_admin, is_owner = _member_context(interaction)
            dj_role_id, has_dj = _has_guild_dj_role(self.guild_id, roles)
            try:
                queue_service.control_playback(
                    guild_id=self.guild_id,
                    action="stop",
                    actor_id=uid,
                    user_roles=roles,
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=dj_role_id,
                    has_dj_role=has_dj,
                )
                asyncio.create_task(bot.apply_web_control(self.guild_id, "stop"))
                stop_emb = _make_embed(
                    title="⏹️ Pemutaran Dihentikan",
                    description=f"Pemutaran dihentikan dan antrean dibersihkan oleh **{interaction.user.display_name}**.",
                    color=0xEF4444,
                    category_label="Athenaa Music Controller",
                )
                await interaction.response.edit_message(embed=stop_emb, view=self)
            except (PermissionError, ValueError, KeyError) as exc:
                await self._send_denied(interaction, str(exc))

        async def _on_loop(self, interaction: discord.Interaction) -> None:
            st = queue_service.get_state(self.guild_id)
            cycle = {"off": "queue", "queue": "one", "one": "off"}
            next_mode = cycle.get(st.loop_mode, "off")
            uid, _, roles, is_admin, is_owner = _member_context(interaction)
            dj_role_id, has_dj = _has_guild_dj_role(self.guild_id, roles)
            try:
                queue_service.control_playback(
                    guild_id=self.guild_id,
                    action="loop",
                    actor_id=uid,
                    user_roles=roles,
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=dj_role_id,
                    has_dj_role=has_dj,
                    value=next_mode,
                )
                asyncio.create_task(bot._notify_web(self.guild_id))
                await interaction.response.edit_message(
                    embed=_build_now_playing_embed(self.guild_id),
                    view=self,
                )
            except (PermissionError, ValueError, KeyError) as exc:
                await self._send_denied(interaction, str(exc))

        async def _on_shuffle(self, interaction: discord.Interaction) -> None:
            st = queue_service.get_state(self.guild_id)
            if len(st.queue) < 2:
                await interaction.response.send_message(
                    "ℹ️ Minimal harus ada 2 lagu di antrean untuk diacak.",
                    ephemeral=True,
                )
                return
            uid, _, roles, is_admin, is_owner = _member_context(interaction)
            dj_role_id, has_dj = _has_guild_dj_role(self.guild_id, roles)
            try:
                queue_service.control_playback(
                    guild_id=self.guild_id,
                    action="shuffle",
                    actor_id=uid,
                    user_roles=roles,
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=dj_role_id,
                    has_dj_role=has_dj,
                )
                asyncio.create_task(bot._notify_web(self.guild_id))
                await interaction.response.edit_message(
                    embed=_build_now_playing_embed(self.guild_id),
                    view=self,
                )
            except (PermissionError, ValueError, KeyError) as exc:
                await self._send_denied(interaction, str(exc))

        async def _on_vol_down(self, interaction: discord.Interaction) -> None:
            st = queue_service.get_state(self.guild_id)
            new_vol = max(10, st.volume - 10)
            uid, _, roles, is_admin, is_owner = _member_context(interaction)
            dj_role_id, has_dj = _has_guild_dj_role(self.guild_id, roles)
            try:
                queue_service.control_playback(
                    guild_id=self.guild_id,
                    action="volume",
                    actor_id=uid,
                    user_roles=roles,
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=dj_role_id,
                    has_dj_role=has_dj,
                    value=new_vol,
                )
                asyncio.create_task(bot.apply_web_control(self.guild_id, "volume", new_vol))
                await interaction.response.edit_message(
                    embed=_build_now_playing_embed(self.guild_id),
                    view=self,
                )
            except (PermissionError, ValueError, KeyError) as exc:
                await self._send_denied(interaction, str(exc))

        async def _on_vol_up(self, interaction: discord.Interaction) -> None:
            st = queue_service.get_state(self.guild_id)
            new_vol = min(100, st.volume + 10)
            uid, _, roles, is_admin, is_owner = _member_context(interaction)
            dj_role_id, has_dj = _has_guild_dj_role(self.guild_id, roles)
            try:
                queue_service.control_playback(
                    guild_id=self.guild_id,
                    action="volume",
                    actor_id=uid,
                    user_roles=roles,
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=dj_role_id,
                    has_dj_role=has_dj,
                    value=new_vol,
                )
                asyncio.create_task(bot.apply_web_control(self.guild_id, "volume", new_vol))
                await interaction.response.edit_message(
                    embed=_build_now_playing_embed(self.guild_id),
                    view=self,
                )
            except (PermissionError, ValueError, KeyError) as exc:
                await self._send_denied(interaction, str(exc))

        async def _on_autoplay(self, interaction: discord.Interaction) -> None:
            st = queue_service.get_state(self.guild_id)
            next_auto = not st.autoplay
            uid, _, roles, is_admin, is_owner = _member_context(interaction)
            dj_role_id, has_dj = _has_guild_dj_role(self.guild_id, roles)
            try:
                queue_service.control_playback(
                    guild_id=self.guild_id,
                    action="autoplay",
                    actor_id=uid,
                    user_roles=roles,
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=dj_role_id,
                    has_dj_role=has_dj,
                    value=next_auto,
                )
                try:
                    with db_manager.transaction() as conn:
                        conn.execute(
                            "UPDATE guild_settings SET autoplay = ?, updated_at = ? WHERE guild_id = ?",
                            (1 if st.autoplay else 0, datetime.now(timezone.utc).isoformat(), self.guild_id),
                        )
                except Exception:
                    pass
                asyncio.create_task(bot.apply_web_control(self.guild_id, "autoplay", st.autoplay))
                await interaction.response.edit_message(
                    embed=_build_now_playing_embed(self.guild_id),
                    view=self,
                )
            except (PermissionError, ValueError, KeyError) as exc:
                await self._send_denied(interaction, str(exc))

        async def _on_mode_247(self, interaction: discord.Interaction) -> None:
            st = queue_service.get_state(self.guild_id)
            next_247 = not st.mode_247
            uid, _, roles, is_admin, is_owner = _member_context(interaction)
            dj_role_id, has_dj = _has_guild_dj_role(self.guild_id, roles)
            try:
                queue_service.control_playback(
                    guild_id=self.guild_id,
                    action="mode_247",
                    actor_id=uid,
                    user_roles=roles,
                    is_admin=is_admin,
                    is_owner=is_owner,
                    dj_role_id=dj_role_id,
                    has_dj_role=has_dj,
                    value=next_247,
                )
                try:
                    with db_manager.transaction() as conn:
                        conn.execute(
                            "UPDATE guild_settings SET mode_247 = ?, updated_at = ? WHERE guild_id = ?",
                            (1 if st.mode_247 else 0, datetime.now(timezone.utc).isoformat(), self.guild_id),
                        )
                except Exception:
                    pass
                asyncio.create_task(bot.apply_web_control(self.guild_id, "mode_247", st.mode_247))
                await interaction.response.edit_message(
                    embed=_build_now_playing_embed(self.guild_id),
                    view=self,
                )
            except (PermissionError, ValueError, KeyError) as exc:
                await self._send_denied(interaction, str(exc))

        async def _on_lyrics(self, interaction: discord.Interaction) -> None:
            st = queue_service.get_state(self.guild_id)
            if not st.current_track:
                await interaction.response.send_message("⏹️ Tidak ada lagu yang sedang diputar.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            tr = st.current_track
            res = await asyncio.to_thread(lyrics_service.get_lyrics, tr.title, tr.artist)
            if not res.found:
                await interaction.followup.send(
                    embed=_make_embed(
                        title=f"🎤 Lirik Belum Tersedia: {tr.title}",
                        description=res.message or "Belum ditemukan di LRCLIB.",
                        color=0xF59E0B,
                    ),
                    ephemeral=True,
                )
                return
            snippet = (
                res.plain_lyrics[:1800]
                if res.plain_lyrics
                else "\n".join(f"`[{_format_mmss(int(l.time_sec))}]` {l.text}" for l in res.synced_lines[:28])
            )
            lyr_emb = _make_embed(
                title=f"🎤 Lirik: {res.track_name} — {res.artist_name}",
                description=snippet or "Lirik tersedia di Web Player.",
                color=0xDC95FF,
                category_label="LRCLIB Real-Time Lyrics",
            )
            await interaction.followup.send(embed=lyr_emb, ephemeral=True)

        async def _on_queue(self, interaction: discord.Interaction) -> None:
            st = queue_service.get_state(self.guild_id)
            if not st.queue:
                await interaction.response.send_message(
                    "📭 Belum ada lagu berikutnya di dalam antrean.",
                    ephemeral=True,
                )
                return
            q_lines = [
                f"`#{it.position}` **{it.title}** — *{it.artist}* (`{_format_mmss(it.duration_sec)}`) • oleh **{it.requester_name}**"
                for it in st.queue[:10]
            ]
            q_emb = _make_embed(
                title=f"📋 Daftar Antrean ({len(st.queue)} Lagu)",
                description="\n".join(q_lines),
                color=0x38BDF8,
                category_label=f"Voice: {st.voice_channel_name}",
            )
            await interaction.response.send_message(embed=q_emb, ephemeral=True)

        async def _on_refresh(self, interaction: discord.Interaction) -> None:
            await interaction.response.edit_message(
                embed=_build_now_playing_embed(self.guild_id),
                view=self,
            )

    # =========================================================================
    # Music & Voice Slash Commands (Modern Rich Embeds)
    # =========================================================================
<<<<<<< HEAD
    @bot.tree.command(name="play", description="Putar lagu/playlist dari judul/penyanyi, URL YouTube, Spotify Track/Playlist, atau Radio")
=======
    @bot.tree.command(name="play", description="Putar lagu atau playlist langsung dari judul/penyanyi, URL YouTube, Spotify Track/Playlist, atau Radio")
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
    @app_commands.describe(query="Ketik judul lagu & penyanyi (pilih dari dropdown) atau tempel URL YouTube/Spotify (Track/Playlist/Album)")
    async def cmd_play(interaction: discord.Interaction, query: str) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, uname, roles, is_admin, is_owner = _member_context(interaction)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)

        # Wajibkan user berada di Voice Channel sebelum bisa memutar lagu
        user_vc = (
            interaction.user.voice.channel
            if isinstance(interaction.user, discord.Member) and interaction.user.voice
            else None
        )
        if not user_vc:
            await interaction.response.send_message(
                embed=_make_embed(
                    title="🔊 Masuk ke Voice Channel Dulu!",
                    description="Kamu harus bergabung ke **Voice Channel** di server ini terlebih dahulu sebelum memutar musik.",
                    color=0xEF4444,
                    category_label="Athenaa Voice Guard",
                ),
                ephemeral=True,
            )
            return

        # Jika bot sudah aktif di Voice Channel lain bersama member lain, tolak agar bot tidak pindah sendiri
        bot_vc: Optional[discord.VoiceClient] = interaction.guild.voice_client if interaction.guild else None  # type: ignore
        if bot_vc and bot_vc.is_connected() and bot_vc.channel and bot_vc.channel.id != user_vc.id:
            humans_in_bot_vc = [m for m in bot_vc.channel.members if not m.bot]
            if humans_in_bot_vc:
                await interaction.response.send_message(
                    embed=_make_embed(
                        title="🔒 Bot Sedang Dipakai di Voice Channel Lain",
                        description=(
                            f"Athenaa sedang memutar musik di **{bot_vc.channel.name}**.\n"
                            f"Silakan masuk ke **{bot_vc.channel.name}** atau pindahkan bot secara manual jika ingin memutar lagu."
                        ),
                        color=0xF59E0B,
                        category_label="Athenaa Voice Guard",
                    ),
                    ephemeral=True,
                )
                return
            else:
                # Jika channel lama bot sudah kosong melompong (0 manusia), izinkan pindah ke channel user
                await bot_vc.move_to(user_vc)

        await interaction.response.defer()
        st_init = queue_service.get_state(guild_id)
        st_init.voice_channel_id = str(user_vc.id)
        st_init.voice_channel_name = user_vc.name
        await bot.ensure_voice_connected(guild_id, st_init.voice_channel_id, uid)

        kind, target = classify_music_input(query)
        if kind in ("spotify_playlist", "spotify_album", "youtube_playlist"):
            try:
                pl_data = await asyncio.to_thread(extract_spotify_playlist_tracks, query, 30)
                tracks: List[TrackCandidate] = pl_data.get("tracks") or []
                pl_name = str(
                    pl_data.get("playlist_name")
                    or ("YouTube Playlist" if kind == "youtube_playlist" else "Spotify Playlist")
                )
                if not tracks:
                    err_emb = _make_embed(
                        title="❌ Playlist Kosong / Tidak Terbaca",
                        description="Tidak ditemukan daftar lagu pada tautan playlist tersebut.",
                        color=0xEF4444,
                        category_label="Athenaa Music Engine",
                    )
                    await interaction.followup.send(embed=err_emb)
                    return

                st_check = queue_service.get_state(guild_id)
                replace_seed = bot._is_unplayed_seed_track(guild_id, st_check)
                started_first = False
                for idx, cand in enumerate(tracks):
                    _, started = queue_service.add_track(
                        guild_id=guild_id,
                        title=cand.title,
                        artist=cand.artist,
                        album=pl_name,
                        duration_sec=cand.duration_sec,
                        source_type=cand.source_type,
                        source_url=cand.source_url,
                        stream_url=cand.stream_url,
                        thumbnail_url=cand.thumbnail_url,
                        requester_id=uid,
                        requester_name=uname,
                        play_now=(idx == 0 and (st_check.current_track is None or replace_seed)),
                        user_roles=roles,
                        is_admin=is_admin,
                        is_owner=is_owner,
                        dj_role_id=dj_role_id,
                        has_dj_role=has_dj,
                    )
                    if started:
                        started_first = True

                if started_first:
                    asyncio.create_task(bot.start_or_sync_voice_playback(guild_id, uid))
                else:
                    asyncio.create_task(bot._notify_web(guild_id))

                source_label = "YouTube Playlist" if kind == "youtube_playlist" else "Spotify Playlist / Album"
                pl_emb = _make_embed(
                    title=f"🎶 {source_label} Dimuat: {pl_name}",
                    description=f"Berhasil menambahkan **{len(tracks)} lagu** langsung ke antrean server.",
                    color=0xDC95FF,
                    category_label=f"Direct {source_label} Player",
                    thumbnail_url=tracks[0].thumbnail_url if tracks else "",
                )
                preview_lines = "\n".join(
                    f"`#{i}` **{t.title}** — {t.artist} (`{_format_mmss(t.duration_sec)}`)"
                    for i, t in enumerate(tracks[:5], start=1)
                )
                pl_emb.add_field(name="Daftar Lagu Awal", value=preview_lines or "—", inline=False)
                pl_emb.add_field(name="Diminta Oleh", value=f"👤 **{uname}**", inline=True)
                pl_emb.add_field(name="Total Lagu", value=f"🎵 **{len(tracks)} Track**", inline=True)
                await interaction.followup.send(embed=pl_emb, view=MusicPlayerControlView(guild_id))
                return
            except Exception as exc:
                err_emb = _make_embed(
                    title="❌ Gagal Memuat Playlist",
                    description=str(exc),
                    color=0xEF4444,
                    category_label="Athenaa Music Engine",
                )
                await interaction.followup.send(embed=err_emb)
                return

        try:
            if kind == "spotify_track":
                cand = await asyncio.to_thread(resolve_spotify_link, query)
            elif kind == "youtube":
                yt_cand = await asyncio.to_thread(resolve_youtube_link, query)
                if yt_cand:
                    cand = yt_cand
                else:
                    results = await asyncio.to_thread(search_songs_with_singer, query, 3)
                    if not results:
                        err_emb = _make_embed(
                            title="🔍 Video YouTube Tidak Dapat Diputar",
                            description=f"Tidak dapat memuat audio untuk tautan YouTube: `{query}`.",
                            color=0xEF4444,
                            category_label="Athenaa Music Search",
                        )
                        await interaction.followup.send(embed=err_emb)
                        return
                    cand = results[0]
            else:
                search_q = target if (kind == "search_query" and target) else query
                results = await asyncio.to_thread(search_songs_with_singer, search_q, 3)
                if not results:
                    err_emb = _make_embed(
                        title="🔍 Lagu Tidak Ditemukan",
                        description=f"Tidak ditemukan lagu untuk kata kunci: `{query}`.",
                        color=0xEF4444,
                        category_label="Athenaa Music Search",
                    )
                    await interaction.followup.send(embed=err_emb)
                    return
                cand = results[0]
        except Exception as exc:
            err_emb = _make_embed(
                title="❌ Gagal Memproses Lagu",
                description=str(exc),
                color=0xEF4444,
                category_label="Athenaa Music Search",
            )
            await interaction.followup.send(embed=err_emb)
            return

        st_pre = queue_service.get_state(guild_id)
        should_play_now = bot._is_unplayed_seed_track(guild_id, st_pre)

        item, started = queue_service.add_track(
            guild_id=guild_id,
            title=cand.title,
            artist=cand.artist,
            album="",
            duration_sec=cand.duration_sec,
            source_type=cand.source_type,
            source_url=cand.source_url,
            stream_url=cand.stream_url,
            thumbnail_url=cand.thumbnail_url,
            requester_id=uid,
            requester_name=uname,
            play_now=should_play_now,
            user_roles=roles,
            is_admin=is_admin,
            is_owner=is_owner,
            dj_role_id=dj_role_id,
            has_dj_role=has_dj,
        )

        st = queue_service.get_state(guild_id)
        if started or should_play_now:
            asyncio.create_task(bot.start_or_sync_voice_playback(guild_id, uid))
            emb = _build_now_playing_embed(guild_id)
            await interaction.followup.send(embed=emb, view=MusicPlayerControlView(guild_id))
        else:
            asyncio.create_task(bot._notify_web(guild_id))
            emb = _make_embed(
                title=f"➕ Ditambahkan ke Antrean (#{item.position})",
                description=f"🎵 **{item.title}**\n🎤 **Penyanyi:** {item.artist}",
                color=0xDC95FF,
                category_label=f"Athenaa Queue System • Voice: {st.voice_channel_name}",
                thumbnail_url=item.thumbnail_url,
            )
            emb.add_field(name="Durasi", value=f"⏱️ `{_format_mmss(item.duration_sec)}`", inline=True)
            emb.add_field(name="Sumber Audio", value=_source_badge(item.source_type), inline=True)
            emb.add_field(name="Diminta Oleh", value=f"👤 **{uname}**", inline=True)
            if st.current_track:
                emb.add_field(
                    name="Sedang Diputar Saat Ini",
                    value=f"🎧 **{st.current_track.title}** — *{st.current_track.artist}*",
                    inline=False,
                )
            await interaction.followup.send(embed=emb, view=MusicPlayerControlView(guild_id))

    @cmd_play.autocomplete("query")
    async def cmd_play_autocomplete(
        _interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        q = (current or "").strip()
        if q.startswith(("http://", "https://")):
            clean_url = q.split("&si=")[0].split("?si=")[0] if "spotify.com" in q else q
            return [app_commands.Choice(name=f"🔗 Putar Langsung URL/Playlist: {clean_url[:68]}", value=clean_url[:100])]
        try:
            candidates = await asyncio.wait_for(
                asyncio.to_thread(search_songs_with_singer, q, 25),
                timeout=1.8,
            )
        except Exception:
            candidates = search_songs_with_singer("", 25)

        choices: List[app_commands.Choice[str]] = []
        for c in candidates[:25]:
            dur = _format_mmss(c.duration_sec)
            label = f"🎵 {c.title} — {c.artist} ({dur})"
            if len(label) > 100:
                label = label[:97] + "..."
            val = (
                c.source_url
                if (c.source_url and len(c.source_url) <= 100 and "results?search_query=" not in c.source_url)
                else f"{c.title} - {c.artist}"[:100]
            )
            choices.append(app_commands.Choice(name=label, value=val))
        return choices

    @bot.tree.command(name="search", description="Cari lagu beserta nama penyanyi dari katalog YouTube & Spotify")
    async def cmd_search(interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        results = await asyncio.to_thread(search_songs_with_singer, query, 10)
        if not results:
            emb = _make_embed(
                title="🔍 Hasil Pencarian Kosong",
                description=f"Tidak ditemukan hasil untuk `{query}`.",
                color=0xEF4444,
                category_label="Athenaa Music Search",
            )
            await interaction.followup.send(embed=emb)
            return

        lines = [
            f"`#{i}` **{r.title}** — *{r.artist}* (`{_format_mmss(r.duration_sec)}`) • {_source_badge(r.source_type)}"
            for i, r in enumerate(results, start=1)
        ]
        emb = _make_embed(
            title=f"🔎 Hasil Pencarian: \"{query}\"",
            description="\n".join(lines) + "\n\n💡 *Gunakan `/play <judul dan penyanyi>` untuk memutar di Voice Channel.*",
            color=0xDC95FF,
            category_label="YouTube & Spotify Catalog",
            thumbnail_url=results[0].thumbnail_url,
        )
        await interaction.followup.send(embed=emb)

    @bot.tree.command(name="nowplaying", description="Tampilkan panel lagu yang sedang diputar beserta tombol kontrol interaktif")
    async def cmd_nowplaying(interaction: discord.Interaction) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        st = queue_service.get_state(guild_id)
        emb = _build_now_playing_embed(guild_id)
        if not st.current_track:
            await interaction.response.send_message(embed=emb)
            return
        await interaction.response.send_message(embed=emb, view=MusicPlayerControlView(guild_id))

    @bot.tree.command(name="queue", description="Tampilkan daftar antrean lagu aktif pada server ini")
    async def cmd_queue(interaction: discord.Interaction, page: int = 1) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        st = queue_service.get_state(guild_id)
        if not st.current_track and not st.queue:
            emb = _make_embed(
                title="📭 Antrean Musik Kosong",
                description="Belum ada lagu di dalam antrean. Gunakan `/play` untuk menambahkan lagu.",
                color=0x64748B,
                category_label="Athenaa Queue Manager",
            )
            await interaction.response.send_message(embed=emb)
            return

        per_page = 8
        total_pages = max(1, (len(st.queue) + per_page - 1) // per_page)
        curr_page = max(1, min(page, total_pages))
        start_idx = (curr_page - 1) * per_page
        slice_items = st.queue[start_idx : start_idx + per_page]

        desc_parts: List[str] = []
        if st.current_track:
            ct = st.current_track
            desc_parts.append(
                f"**▶️ Sedang Diputar:**\n"
                f"**{ct.title}** — *{ct.artist}* (`{_format_mmss(st.position_sec)}/{_format_mmss(ct.duration_sec)}`) • oleh **{ct.requester_name}**\n"
                f"{_build_progress_bar(st.position_sec, ct.duration_sec)}\n"
            )

        if slice_items:
            q_lines = [
                f"`#{it.position}` **{it.title}** — *{it.artist}* (`{_format_mmss(it.duration_sec)}`) • oleh **{it.requester_name}**"
                for it in slice_items
            ]
            desc_parts.append("**📋 Antrean Berikutnya:**\n" + "\n".join(q_lines))
        else:
            desc_parts.append("*Tidak ada lagu berikutnya di antrean.*")

        emb = _make_embed(
            title=f"🎶 Antrean Musik Server ({len(st.queue)} Lagu)",
            description="\n".join(desc_parts),
            color=0xDC95FF,
            category_label=f"Voice: {st.voice_channel_name} • Halaman {curr_page}/{total_pages}",
            thumbnail_url=st.current_track.thumbnail_url if st.current_track else "",
        )
        emb.add_field(
            name="Volume & Loop",
            value=f"🔊 `{st.volume}%` • Loop `{st.loop_mode.upper()}`",
            inline=True,
        )
        emb.add_field(name="Autoplay", value="✅ Aktif" if st.autoplay else "❌ Nonaktif", inline=True)
        emb.add_field(name="Mode 24/7", value="✅ Aktif" if st.mode_247 else "❌ Nonaktif", inline=True)
        await interaction.response.send_message(embed=emb, view=MusicPlayerControlView(guild_id))

    @bot.tree.command(name="remove", description="Hapus lagu tertentu dari daftar antrean berdasarkan nomor urut")
    @app_commands.describe(posisi="Nomor urut lagu di dalam antrean (lihat /queue)")
    async def cmd_remove(interaction: discord.Interaction, posisi: int) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, _, roles, is_admin, is_owner = _member_context(interaction)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)
        st = queue_service.get_state(guild_id)
        if not st.queue:
            await interaction.response.send_message(
                embed=_make_embed(
                    title="📭 Antrean Kosong",
                    description="Tidak ada lagu di dalam antrean untuk dihapus.",
                    color=0xEF4444,
                ),
                ephemeral=True,
            )
            return
        if posisi < 1 or posisi > len(st.queue):
            await interaction.response.send_message(
                embed=_make_embed(
                    title="⚠️ Nomor Urut Tidak Valid",
                    description=f"Masukkan nomor urut antara **1** hingga **{len(st.queue)}**.",
                    color=0xF59E0B,
                ),
                ephemeral=True,
            )
            return

        target = st.queue[posisi - 1]
        try:
            removed = queue_service.remove_item(
                guild_id=guild_id,
                item_id=target.item_id,
                actor_id=uid,
                user_roles=roles,
                is_admin=is_admin,
                is_owner=is_owner,
                dj_role_id=dj_role_id,
                has_dj_role=has_dj,
            )
            await bot._notify_web(guild_id)
            emb = _make_embed(
                title=f"🗑️ Lagu Dihapus dari Antrean (#{posisi})",
                description=(
                    f"🎵 **{removed.title}** — *{removed.artist}*\n"
                    f"👤 Diminta oleh: **{removed.requester_name}**"
                ),
                color=0xDC95FF,
                category_label="Athenaa Queue Manager",
                thumbnail_url=removed.thumbnail_url,
            )
            await interaction.response.send_message(embed=emb)
        except PermissionError as exc:
            await interaction.response.send_message(
                embed=_make_embed(title="🔒 Akses Ditolak", description=str(exc), color=0xEF4444),
                ephemeral=True,
            )

    @bot.tree.command(name="skip", description="Lewati lagu saat ini di Voice Channel")
    async def cmd_skip(interaction: discord.Interaction) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, _, roles, is_admin, is_owner = _member_context(interaction)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)
        try:
            queue_service.control_playback(
                guild_id=guild_id,
                action="skip",
                actor_id=uid,
                user_roles=roles,
                is_admin=is_admin,
                is_owner=is_owner,
                dj_role_id=dj_role_id,
                has_dj_role=has_dj,
            )
            asyncio.create_task(bot.apply_web_control(guild_id, "skip"))
            st = queue_service.get_state(guild_id)
            next_title = f"**{st.current_track.title} — {st.current_track.artist}**" if st.current_track else "Antrean selesai"
            emb = _make_embed(
                title="⏭️ Lagu Dilewati (Skipped)",
                description=f"Sekarang memutar: {next_title}",
                color=0xDC95FF,
                category_label="Athenaa Music Controller",
                thumbnail_url=st.current_track.thumbnail_url if st.current_track else "",
            )
            await interaction.response.send_message(embed=emb)
        except PermissionError as exc:
            err_emb = _make_embed(title="🔒 Akses Ditolak", description=str(exc), color=0xEF4444)
            await interaction.response.send_message(embed=err_emb, ephemeral=True)

    @bot.tree.command(name="pause", description="Jeda pemutaran lagu aktif")
    async def cmd_pause(interaction: discord.Interaction) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, _, roles, is_admin, is_owner = _member_context(interaction)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)
        try:
            queue_service.control_playback(
                guild_id=guild_id,
                action="pause",
                actor_id=uid,
                user_roles=roles,
                is_admin=is_admin,
                is_owner=is_owner,
                dj_role_id=dj_role_id,
                has_dj_role=has_dj,
            )
            asyncio.create_task(bot.apply_web_control(guild_id, "pause"))
            emb = _make_embed(
                title="⏸️ Pemutaran Dijeda",
                description="Gunakan `/resume` atau tombol di bawah untuk melanjutkan lagu.",
                color=0xF59E0B,
                category_label="Athenaa Music Controller",
            )
            await interaction.response.send_message(embed=emb)
        except PermissionError as exc:
            await interaction.response.send_message(
                embed=_make_embed(title="🔒 Akses Ditolak", description=str(exc), color=0xEF4444),
                ephemeral=True,
            )

    @bot.tree.command(name="resume", description="Lanjutkan pemutaran lagu yang dijeda")
    async def cmd_resume(interaction: discord.Interaction) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, _, roles, is_admin, is_owner = _member_context(interaction)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)
        try:
            queue_service.control_playback(
                guild_id=guild_id,
                action="resume",
                actor_id=uid,
                user_roles=roles,
                is_admin=is_admin,
                is_owner=is_owner,
                dj_role_id=dj_role_id,
                has_dj_role=has_dj,
            )
            asyncio.create_task(bot.apply_web_control(guild_id, "resume"))
            emb = _make_embed(
                title="▶️ Pemutaran Dilanjutkan",
                description="Audio di Voice Channel kembali diputar.",
                color=0xDC95FF,
                category_label="Athenaa Music Controller",
            )
            await interaction.response.send_message(embed=emb)
        except PermissionError as exc:
            await interaction.response.send_message(
                embed=_make_embed(title="🔒 Akses Ditolak", description=str(exc), color=0xEF4444),
                ephemeral=True,
            )

    @bot.tree.command(name="stop", description="Hentikan pemutaran dan bersihkan antrean")
    async def cmd_stop(interaction: discord.Interaction) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, _, roles, is_admin, is_owner = _member_context(interaction)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)
        try:
            queue_service.control_playback(
                guild_id=guild_id,
                action="stop",
                actor_id=uid,
                user_roles=roles,
                is_admin=is_admin,
                is_owner=is_owner,
                dj_role_id=dj_role_id,
                has_dj_role=has_dj,
            )
            asyncio.create_task(bot.apply_web_control(guild_id, "stop"))
            emb = _make_embed(
                title="⏹️ Pemutaran Dihentikan",
                description="Seluruh antrean lagu telah dibersihkan.",
                color=0xEF4444,
                category_label="Athenaa Music Controller",
            )
            await interaction.response.send_message(embed=emb)
        except PermissionError as exc:
            await interaction.response.send_message(
                embed=_make_embed(title="🔒 Akses Ditolak", description=str(exc), color=0xEF4444),
                ephemeral=True,
            )

    @bot.tree.command(name="shuffle", description="Acak urutan antrean musik")
    async def cmd_shuffle(interaction: discord.Interaction) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, _, roles, is_admin, is_owner = _member_context(interaction)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)
        try:
            queue_service.control_playback(
                guild_id=guild_id,
                action="shuffle",
                actor_id=uid,
                user_roles=roles,
                is_admin=is_admin,
                is_owner=is_owner,
                dj_role_id=dj_role_id,
                has_dj_role=has_dj,
            )
            await bot._notify_web(guild_id)
            emb = _make_embed(
                title="🔀 Antrean Diacak",
                description="Urutan lagu di dalam antrean server berhasil diacak.",
                color=0xDC95FF,
                category_label="Athenaa Queue Manager",
            )
            await interaction.response.send_message(embed=emb)
        except PermissionError as exc:
            await interaction.response.send_message(
                embed=_make_embed(title="🔒 Akses Ditolak", description=str(exc), color=0xEF4444),
                ephemeral=True,
            )

    @bot.tree.command(name="volume", description="Atur volume suara bot antara 1% hingga 100%")
    async def cmd_volume(interaction: discord.Interaction, persen: int) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, _, roles, is_admin, is_owner = _member_context(interaction)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)
        try:
            queue_service.control_playback(
                guild_id=guild_id,
                action="volume",
                actor_id=uid,
                user_roles=roles,
                is_admin=is_admin,
                is_owner=is_owner,
                dj_role_id=dj_role_id,
                has_dj_role=has_dj,
                value=persen,
            )
            asyncio.create_task(bot.apply_web_control(guild_id, "volume", persen))
            emb = _make_embed(
                title=f"🔊 Volume Diatur ke {persen}%",
                description=_build_progress_bar(persen, 100),
                color=0xDC95FF,
                category_label="Audio Control",
            )
            await interaction.response.send_message(embed=emb)
        except (PermissionError, ValueError) as exc:
            await interaction.response.send_message(
                embed=_make_embed(title="⚠️ Gagal Mengubah Volume", description=str(exc), color=0xEF4444),
                ephemeral=True,
            )

    @bot.tree.command(name="loop", description="Atur mode pengulangan lagu (off, one, queue)")
    async def cmd_loop(interaction: discord.Interaction, mode: str) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, _, roles, is_admin, is_owner = _member_context(interaction)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)
        try:
            queue_service.control_playback(
                guild_id=guild_id,
                action="loop",
                actor_id=uid,
                user_roles=roles,
                is_admin=is_admin,
                is_owner=is_owner,
                dj_role_id=dj_role_id,
                has_dj_role=has_dj,
                value=mode.lower(),
            )
            await bot._notify_web(guild_id)
            emb = _make_embed(
                title=f"🔁 Mode Loop: {mode.upper()}",
                description="Pengaturan pengulangan lagu telah diperbarui.",
                color=0xDC95FF,
                category_label="Athenaa Queue Manager",
            )
            await interaction.response.send_message(embed=emb)
        except (PermissionError, ValueError) as exc:
            await interaction.response.send_message(
                embed=_make_embed(title="⚠️ Mode Loop Tidak Valid", description=str(exc), color=0xEF4444),
                ephemeral=True,
            )

    @bot.tree.command(name="autoplay", description="Aktifkan/nonaktifkan pemutaran lagu lanjutan otomatis saat antrean habis")
    async def cmd_autoplay(interaction: discord.Interaction, aktif: bool) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, uname, roles, is_admin, is_owner = _member_context(interaction)
        st = queue_service.get_state(guild_id)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)
        allowed, reason = check_host_lock_permission(
            user_id=uid,
            user_roles=roles,
            is_admin=is_admin,
            is_owner=is_owner,
            session_host_id=st.host_user_id,
            dj_role_id=dj_role_id,
            action="autoplay",
            has_dj_role=has_dj,
        )
        if not allowed:
            await interaction.response.send_message(
                embed=_make_embed(title="🔒 Akses Ditolak", description=reason, color=0xEF4444),
                ephemeral=True,
            )
            return
        st.autoplay = bool(aktif)
        try:
            with db_manager.transaction() as conn:
                conn.execute(
                    "UPDATE guild_settings SET autoplay = ?, updated_at = ? WHERE guild_id = ?",
                    (1 if st.autoplay else 0, datetime.now(timezone.utc).isoformat(), guild_id),
                )
        except Exception:
            pass
        if not st.autoplay:
            queue_service.prefetched_autoplay.pop(guild_id, None)
        elif st.current_track is None:
            queue_service.advance_track(guild_id)
            if st.current_track:
                asyncio.create_task(bot.start_or_sync_voice_playback(guild_id, uid))
        asyncio.create_task(bot.apply_web_control(guild_id, "autoplay", st.autoplay))
        emb = _make_embed(
            title=f"📻 Autoplay: {'AKTIF' if aktif else 'NONAKTIF'}",
            description="Bot akan otomatis memutar lagu rekomendasi saat antrean habis." if aktif else "Autoplay dinonaktifkan.",
            color=0xDC95FF if aktif else 0x64748B,
            category_label="Athenaa Queue Manager",
        )
        await interaction.response.send_message(embed=emb)

    @bot.tree.command(name="247", description="Pertahankan koneksi bot di voice channel selama 24/7")
    async def cmd_247(interaction: discord.Interaction, aktif: bool) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, uname, roles, is_admin, is_owner = _member_context(interaction)
        st = queue_service.get_state(guild_id)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)
        allowed, reason = check_host_lock_permission(
            user_id=uid,
            user_roles=roles,
            is_admin=is_admin,
            is_owner=is_owner,
            session_host_id=st.host_user_id,
            dj_role_id=dj_role_id,
            action="mode_247",
            has_dj_role=has_dj,
        )
        if not allowed:
            await interaction.response.send_message(
                embed=_make_embed(title="🔒 Akses Ditolak", description=reason, color=0xEF4444),
                ephemeral=True,
            )
            return
        st.mode_247 = bool(aktif)
        try:
            with db_manager.transaction() as conn:
                conn.execute(
                    "UPDATE guild_settings SET mode_247 = ?, updated_at = ? WHERE guild_id = ?",
                    (1 if st.mode_247 else 0, datetime.now(timezone.utc).isoformat(), guild_id),
                )
        except Exception:
            pass
        if aktif:
            asyncio.create_task(bot.ensure_voice_connected(guild_id, st.voice_channel_id, str(interaction.user.id)))
        asyncio.create_task(bot.apply_web_control(guild_id, "mode_247", st.mode_247))
        emb = _make_embed(
            title=f"🌙 Mode 24/7: {'AKTIF' if aktif else 'NONAKTIF'}",
            description="Bot akan tetap berada di Voice Channel selama 24/7." if aktif else "Mode 24/7 dinonaktifkan.",
            color=0xDC95FF if aktif else 0x64748B,
            category_label="Athenaa Voice Engine",
        )
        await interaction.response.send_message(embed=emb)

    @bot.tree.command(name="lyrics", description="Tampilkan lirik lagu yang sedang diputar atau berdasarkan judul")
    async def cmd_lyrics(interaction: discord.Interaction, judul: Optional[str] = None) -> None:
        await interaction.response.defer()
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        st = queue_service.get_state(guild_id)
        title = judul or (st.current_track.title if st.current_track else "")
        artist = "" if judul else (st.current_track.artist if st.current_track else "")

        if not title:
            await interaction.followup.send(
                embed=_make_embed(
                    title="🎤 Judul Lagu Diperlukan",
                    description="Tidak ada lagu aktif. Masukkan parameter `judul` pada `/lyrics`.",
                    color=0xEF4444,
                )
            )
            return

        res = await asyncio.to_thread(lyrics_service.get_lyrics, title, artist)
        if not res.found:
            await interaction.followup.send(
                embed=_make_embed(
                    title=f"🎤 Lirik Belum Ditemukan: {title}",
                    description=res.message or "Belum tersedia di database LRCLIB.",
                    color=0xF59E0B,
                    category_label="LRCLIB Lyrics Engine",
                )
            )
            return

        snippet = res.plain_lyrics[:1800] if res.plain_lyrics else "\n".join(l.text for l in res.synced_lines[:30])
        emb = _make_embed(
            title=f"🎤 {res.track_name} — {res.artist_name}",
            description=snippet or "Lirik tersedia di Web Player.",
            color=0xDC95FF,
            category_label=f"LRCLIB • {'Synced Lyrics' if res.status == 'synced' else 'Plain Lyrics'}",
        )
        await interaction.followup.send(embed=emb)

    @bot.tree.command(name="leave", description="Putuskan koneksi bot dari Voice Channel")
    async def cmd_leave(interaction: discord.Interaction) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, _, roles, is_admin, is_owner = _member_context(interaction)
        dj_role_id, has_dj = _has_guild_dj_role(guild_id, roles)
        st = queue_service.get_state(guild_id)
        allowed, reason = check_host_lock_permission(
            user_id=uid,
            user_roles=roles,
            is_admin=is_admin,
            is_owner=is_owner,
            session_host_id=st.host_user_id,
            dj_role_id=dj_role_id,
            action="stop",
            has_dj_role=has_dj,
        )
        if not allowed:
            await interaction.response.send_message(
                embed=_make_embed(title="🔒 Akses Ditolak", description=reason, color=0xEF4444),
                ephemeral=True,
            )
            return

        st.mode_247 = False
        queue_service.control_playback(
            guild_id=guild_id,
            action="stop",
            actor_id=uid,
            user_roles=roles,
            is_admin=True,
            is_owner=False,
            dj_role_id=dj_role_id,
            has_dj_role=has_dj,
        )
        bot._playback_gen[guild_id] = bot._playback_gen.get(guild_id, 0) + 1
        bot._active_vc_track_id.pop(guild_id, None)
        bot._track_stopped_mono.pop(guild_id, None)
        if interaction.guild and interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect(force=True)
        await bot._notify_web(guild_id)
        await interaction.response.send_message(
            embed=_make_embed(
                title="👋 Keluar dari Voice Channel",
                description="Koneksi voice diputus dan antrean sesi telah dibersihkan.",
                color=0xDC95FF,
            )
        )

    # =========================================================================
    # Academic & Waskita Slash Commands (/tugas, /tugas_list, /tugas_add, /tugas_done, /tugas_hapus)
    # =========================================================================
    async def _send_tugas_list_response(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        tasks = academy_service.get_active_tasks_for_daily_reminder(guild_id)
        discord_files, module_metas = _collect_task_module_files(
            guild_id,
            task_ids=[t.task_id for t in tasks] if tasks else None,
        )

        if not tasks:
            desc_text = (
                "Semua tugas telah diselesaikan atau belum ada tugas aktif!\n"
                "🔄 Sistem menyinkronkan tugas Waskita/Moodle otomatis setiap **1 jam** "
                "dan menghapus otomatis tugas yang sudah melewati tenggat waktu.\n"
                "Gunakan `/tugas_add` atau `/sync_waskita` untuk menyinkronkan tugas baru."
            )
            if module_metas:
                mod_lines = "\n".join(
                    f"• 📄 **{m['original_filename']}** *(oleh {m['uploaded_by']})*"
                    for m in module_metas
                )
                desc_text += f"\n\n**📦 Lampiran Modul Tersedia ({len(module_metas)} File):**\n{mod_lines}"

            emb = _make_embed(
                title="🎓 Tidak Ada Tugas Akademik Aktif",
                description=desc_text,
                color=0xDC95FF,
                category_label="Athenaa Academic & Waskita Reminder",
            )
            if discord_files:
                await interaction.followup.send(embed=emb, files=discord_files)
            else:
                await interaction.followup.send(embed=emb)
            return

        wib_now = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Jakarta"))
        emb = build_daily_task_reminder_embed(
            tasks=tasks,
            date_wib_str=wib_now.strftime("%Y-%m-%d"),
            now_ref=wib_now,
            module_metas=module_metas,
        )
        if discord_files:
            await interaction.followup.send(embed=emb, files=discord_files)
        else:
            await interaction.followup.send(embed=emb)

    @bot.tree.command(
        name="tugas",
        description="Lihat daftar tugas akademik aktif beserta pengiriman file modul lampiran",
    )
    async def cmd_tugas(interaction: discord.Interaction) -> None:
        await _send_tugas_list_response(interaction)

    @bot.tree.command(
        name="tugas_list",
        description="Lihat daftar tugas akademik aktif beserta pengiriman file modul lampiran",
    )
    async def cmd_tugas_list(interaction: discord.Interaction) -> None:
        await _send_tugas_list_response(interaction)

    @bot.tree.command(
        name="tugas_add",
        description="Tambahkan tugas akademik baru secara manual (bisa sekaligus lampirkan file modul)",
    )
    async def cmd_tugas_add(
        interaction: discord.Interaction,
        mata_kuliah: str,
        judul: str,
        deadline_iso: str,
        file_modul: Optional[discord.Attachment] = None,
    ) -> None:
        await interaction.response.defer()
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        creator_name = interaction.user.display_name
        task = academy_service.create_task(
            guild_id=guild_id,
            course_name=mata_kuliah,
            title=judul,
            deadline_iso=deadline_iso,
            created_by=creator_name,
        )

        attached_files_to_send: List[Any] = []
        modul_status_text = ""

        if file_modul is not None:
            raw_bytes = await file_modul.read()
            ok, err_msg, stored_name = sanitize_and_validate_attachment(
                file_modul.filename,
                raw_bytes[:64] if raw_bytes else b"",
                max_mb=15,
            )
            if ok and len(raw_bytes) <= 15 * 1024 * 1024:
                target_dirs = [Path("modules")]
                if getattr(settings, "modules_dir", None):
                    target_dirs.insert(0, Path(settings.modules_dir))
                saved_fp: Optional[Path] = None
                for m_dir in target_dirs:
                    try:
                        m_dir.mkdir(parents=True, exist_ok=True)
                        fp = m_dir / stored_name
                        fp.write_bytes(raw_bytes)
                        if saved_fp is None:
                            saved_fp = fp
                    except Exception:
                        pass

                att_id = f"att-{uuid.uuid4().hex[:10]}"
                now_iso = datetime.now(timezone.utc).isoformat()
                with db_manager.transaction() as conn:
                    conn.execute(
                        """
                        INSERT INTO task_attachments (
                            attachment_id, task_id, guild_id, original_filename,
                            stored_filename, mime_type, size_bytes, uploaded_by, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            att_id,
                            task.task_id,
                            guild_id,
                            file_modul.filename,
                            stored_name,
                            file_modul.content_type or "application/pdf",
                            len(raw_bytes),
                            creator_name,
                            now_iso,
                        ),
                    )
                if saved_fp and saved_fp.is_file() and DISCORD_PY_AVAILABLE:
                    attached_files_to_send.append(
                        discord.File(str(saved_fp), filename=file_modul.filename)
                    )
                modul_status_text = f"\n📎 **File Modul:** `{file_modul.filename}` *(Tersimpan & Terlampir)*"
            else:
                modul_status_text = f"\n⚠️ **File Modul Ditolak:** {err_msg}"

        emb = _make_embed(
            title="✅ Tugas Akademik Ditambahkan",
            description=f"**{task.title}** berhasil disimpan ke server.{modul_status_text}",
            color=0xDC95FF,
            category_label="Athenaa Academic Tracker",
        )
        emb.add_field(name="Mata Kuliah", value=task.course_name, inline=True)
        emb.add_field(name="ID Tugas", value=f"`{task.task_id}`", inline=True)
        emb.add_field(name="Deadline", value=f"`{task.deadline_iso[:16].replace('T', ' ')}`", inline=True)

        if attached_files_to_send:
            await interaction.followup.send(embed=emb, files=attached_files_to_send)
        else:
            await interaction.followup.send(embed=emb)

    @bot.tree.command(
        name="tugas_done",
        description="Tandai tugas akademik sebagai selesai dan hentikan reminder",
    )
    async def cmd_tugas_done(interaction: discord.Interaction, task_id: str) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        ok = academy_service.set_task_completion(
            guild_id=guild_id,
            task_id=task_id.strip(),
            completed=True,
            actor_name=interaction.user.display_name,
        )
        if not ok:
            await interaction.response.send_message(
                embed=_make_embed(
                    title="❌ Tugas Tidak Ditemukan",
                    description=f"ID tugas `{task_id}` tidak ditemukan di server ini. Cek ID melalui `/tugas`.",
                    color=0xEF4444,
                ),
                ephemeral=True,
            )
            return
        emb = _make_embed(
            title="🎉 Tugas Ditandai Selesai!",
            description=f"Tugas `{task_id}` telah diselesaikan oleh **{interaction.user.display_name}**. Pengingat berikutnya dihentikan.",
            color=0xDC95FF,
            category_label="Athenaa Academic Tracker",
        )
        await interaction.response.send_message(embed=emb)

    @bot.tree.command(
        name="tugas_hapus",
        description="Hapus tugas akademik dari database berdasarkan ID Tugas",
    )
    async def cmd_tugas_hapus(interaction: discord.Interaction, task_id: str) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        ok = academy_service.delete_task(guild_id, task_id.strip())
        if not ok:
            await interaction.response.send_message(
                embed=_make_embed(
                    title="❌ Gagal Menghapus Tugas",
                    description=f"Tugas dengan ID `{task_id}` tidak ditemukan.",
                    color=0xEF4444,
                ),
                ephemeral=True,
            )
            return
        emb = _make_embed(
            title="🗑️ Tugas Berhasil Dihapus",
            description=f"Tugas `{task_id}` telah dihapus dari database.",
            color=0x38BDF8,
            category_label="Athenaa Academic Tracker",
        )
        await interaction.response.send_message(embed=emb)

    async def _run_waskita_sync(interaction: discord.Interaction, ical_url: Optional[str] = None) -> None:
        await interaction.response.defer()
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        try:
            res = await asyncio.to_thread(
                academy_service.sync_moodle_ics_content,
                guild_id,
                "",
                interaction.user.display_name,
                ical_url or "",
            )
            purged_info = (
                f"\n🗑️ **Tugas Lewat Deadline Dihapus:** `{res.get('purged_expired', 0)}`"
                if "purged_expired" in res
                else ""
            )
            emb = _make_embed(
                title="🔄 Sinkronisasi Kalender Waskita Selesai",
                description=(
                    f"Data kalender akademik Waskita berhasil disinkronkan tanpa duplikasi UID.\n\n"
                    f"📥 **Tugas Baru:** `{res['inserted']}`\n"
                    f"♻️ **Tugas Diperbarui:** `{res['updated']}`"
                    f"{purged_info}\n"
                    f"🔗 **Sumber Konfigurasi:** `{str(res.get('source_used', 'Waskita .env')).replace('Moodle', 'Waskita')}`"
                ),
                color=0xDC95FF,
                category_label="Waskita iCal & Credentials Sync",
            )
            await interaction.followup.send(embed=emb)
        except Exception as exc:
            await interaction.followup.send(
                embed=_make_embed(title="❌ Gagal Sinkronisasi Waskita", description=str(exc), color=0xEF4444)
            )

    @bot.tree.command(name="sync_waskita", description="Sinkronkan tugas dari Kalender Waskita (.ics atau Kredensial .env)")
    async def cmd_sync_waskita(interaction: discord.Interaction, ical_url: Optional[str] = None) -> None:
        await _run_waskita_sync(interaction, ical_url)

    @bot.tree.command(name="sync_moodle", description="Sinkronkan tugas dari Kalender Waskita (.ics atau Kredensial .env)")
    async def cmd_sync_moodle(interaction: discord.Interaction, ical_url: Optional[str] = None) -> None:
        await _run_waskita_sync(interaction, ical_url)

    # =========================================================================
    # Student Productivity Addon Commands (/pomodoro, /ipk, /kelompok)
    # =========================================================================
    @bot.tree.command(name="pomodoro", description="Mulai timer fokus belajar Pomodoro di Discord (+30 EXP)")
    async def cmd_pomodoro(
        interaction: discord.Interaction,
        fokus_menit: int = 25,
        istirahat_menit: int = 5,
        topik: str = "Belajar Mandiri & Tugas Kuliah",
    ) -> None:
        fokus_clamped = max(1, min(120, fokus_menit))
        istirahat_clamped = max(1, min(60, istirahat_menit))
        guild_id = str(interaction.guild_id or settings.main_guild_id)

        leveled_up, lvl, c_exp, m_exp = leveling_service.process_voice_activity(
            guild_id=guild_id,
            user_id=str(interaction.user.id),
            username=interaction.user.name,
            display_name=interaction.user.display_name,
            activity_type="pomodoro",
            cooldown_seconds=30,
            exp_gain=30,
        )

        emb = _make_embed(
            title=f"🍅 Sesi Fokus Pomodoro Dimulai ({fokus_clamped} Menit)",
            description=(
                f"🎯 **Topik Fokus:** {topik}\n"
                f"👤 **Peserta:** {interaction.user.mention}\n\n"
                f"⏳ **Waktu Fokus:** `{fokus_clamped} menit` → **Istirahat:** `{istirahat_clamped} menit`\n"
                f"✨ **Bonus Produktivitas:** `+30 EXP` (Level **{lvl}** • `{c_exp}/{m_exp} EXP`)"
                + ("\n🎉 **LEVEL UP!**" if leveled_up else "")
            ),
            color=0x38BDF8,
            category_label="Utilitas Mahasiswa • Pomodoro Timer",
            thumbnail_url=interaction.user.display_avatar.url if interaction.user.display_avatar else "",
        )
        await interaction.response.send_message(embed=emb)

    @bot.tree.command(name="ipk", description="Hitung simulasi IP/IPK dari daftar SKS:Nilai (contoh: 3:A, 4:AB, 3:B+, 2:B)")
    async def cmd_ipk(interaction: discord.Interaction, sks_nilai: str) -> None:
        grade_map = {
            "A": 4.0,
            "A-": 3.7,
            "AB": 3.5,
            "B+": 3.3,
            "B": 3.0,
            "B-": 2.7,
            "BC": 2.5,
            "C+": 2.3,
            "C": 2.0,
            "D": 1.0,
            "E": 0.0,
        }
        total_sks = 0
        total_bobot = 0.0
        detail_rows: List[str] = []

        for raw_pair in sks_nilai.replace(";", ",").split(","):
            pair = raw_pair.strip()
            if ":" not in pair:
                continue
            sks_str, grade_str = pair.split(":", 1)
            try:
                sks = int(sks_str.strip())
                g_clean = grade_str.strip().upper()
                bobot = grade_map.get(g_clean)
                if bobot is None or sks <= 0:
                    continue
                total_sks += sks
                total_bobot += sks * bobot
                detail_rows.append(f"• `{sks} SKS` × Nilai **{g_clean}** (`{bobot:.1f}`) = `{sks * bobot:.1f}`")
            except ValueError:
                continue

        if total_sks == 0:
            await interaction.response.send_message(
                embed=_make_embed(
                    title="⚠️ Format Input IPK Tidak Valid",
                    description="Gunakan format `SKS:Nilai` dipisahkan koma, contoh:\n`/ipk sks_nilai: 3:A, 4:AB, 3:B+, 2:A`",
                    color=0xEF4444,
                    category_label="Kalkulator IP/IPK Mahasiswa",
                ),
                ephemeral=True,
            )
            return

        ipk = total_bobot / total_sks
        if ipk >= 3.51:
            predikat = "🌟 Cum Laude (Dengan Pujian)"
        elif ipk >= 3.01:
            predikat = "✨ Sangat Memuaskan"
        elif ipk >= 2.76:
            predikat = "👍 Memuaskan"
        else:
            predikat = "📘 Cukup / Perlu Peningkatan"

        emb = _make_embed(
            title=f"🎓 Hasil Perhitungan IP / IPK: {ipk:.2f} / 4.00",
            description="\n".join(detail_rows),
            color=0x38BDF8,
            category_label="Utilitas Mahasiswa • Kalkulator Akademik",
        )
        emb.add_field(name="Total SKS", value=f"📚 **{total_sks} SKS**", inline=True)
        emb.add_field(name="Total Mutu", value=f"📊 **{total_bobot:.1f}**", inline=True)
        emb.add_field(name="Predikat", value=predikat, inline=False)
        await interaction.response.send_message(embed=emb)

    @bot.tree.command(name="kelompok", description="Acak pembagian kelompok tugas dari daftar nama (koma) atau anggota Voice Channel")
    async def cmd_kelompok(
        interaction: discord.Interaction,
        jumlah_kelompok: int = 2,
        daftar_nama: Optional[str] = None,
    ) -> None:
        names: List[str] = []
        if daftar_nama and daftar_nama.strip():
            names = [n.strip() for n in daftar_nama.replace(";", ",").split(",") if n.strip()]
        elif isinstance(interaction.user, discord.Member) and interaction.user.voice and interaction.user.voice.channel:
            names = [m.display_name for m in interaction.user.voice.channel.members if not m.bot]

        if len(names) < 2:
            await interaction.response.send_message(
                embed=_make_embed(
                    title="⚠️ Daftar Anggota Kurang",
                    description="Masukkan minimal 2 nama dipisahkan koma (mis. `Budi, Sari, Andi, Dinda`) atau masuk ke Voice Channel terlebih dahulu.",
                    color=0xEF4444,
                    category_label="Generator Kelompok Tugas",
                ),
                ephemeral=True,
            )
            return

        random.shuffle(names)
        k_count = max(1, min(jumlah_kelompok, len(names)))
        groups: List[List[str]] = [[] for _ in range(k_count)]
        for idx, person in enumerate(names):
            groups[idx % k_count].append(person)

        emb = _make_embed(
            title=f"👥 Pembagian {k_count} Kelompok Tugas ({len(names)} Anggota)",
            description="Hasil pengacakan anggota secara adil & merata:",
            color=0x38BDF8,
            category_label="Utilitas Mahasiswa • Randomizer Kelompok",
        )
        for i, grp in enumerate(groups, start=1):
            emb.add_field(
                name=f"Kelompok {i} ({len(grp)} orang)",
                value="\n".join(f"• {p}" for p in grp) or "—",
                inline=True,
            )
        await interaction.response.send_message(embed=emb)

    # =========================================================================
    # Leaderboard & AFK Slash Commands
    # =========================================================================
    @bot.tree.command(name="level", description="Lihat kartu profil Level dan progres EXP (Chat, Join Voice, Speak, Listening, Streaming)")
    async def cmd_level(interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        target = member or interaction.user
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        prof = leveling_service.get_profile(
            guild_id=guild_id,
            user_id=str(target.id),
            username=target.name,
            display_name=target.display_name,
        )
        bar = _build_progress_bar(prof["current_exp"], prof["max_exp"])
        emb = _make_embed(
            title=f"🏆 Profil Level — {prof['display_name']}",
            description=(
                f"📊 **Progres Level {prof['level']}:**\n{bar}\n\n"
                f"💡 **Sumber Perolehan EXP:**\n"
                f"• 💬 Chat Server (`+15 EXP`) • 🔊 Join Voice (`+20 EXP`)\n"
                f"• 🎙️ Speak Voice (`+15 EXP/m`) • 🎧 Listening (`+10 EXP/m`) • 🖥️ Streaming (`+25 EXP/m`)"
            ),
            color=0x8B5CF6,
            category_label="Athenaa Leveling & Leaderboard",
            thumbnail_url=target.display_avatar.url if target.display_avatar else "",
        )
        emb.add_field(name="Level Saat Ini", value=f"⭐ **Lv. {prof['level']}**", inline=True)
        emb.add_field(name="EXP Progres", value=f"`{prof['current_exp']} / {prof['max_exp']} EXP`", inline=True)
        emb.add_field(name="Total Aktivitas", value=f"🔥 `{prof['total_messages']} aktivitas`", inline=True)
        await interaction.response.send_message(embed=emb)

    @bot.tree.command(name="leaderboard", description="Tampilkan Top 15 Leaderboard Server (Chat & Voice Activity)")
    async def cmd_leaderboard(interaction: discord.Interaction) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        board = leveling_service.get_leaderboard(guild_id, limit=15)
        if not board:
            await interaction.response.send_message(
                embed=_make_embed(
                    title="🏆 Leaderboard Server Kosong",
                    description="Belum ada data EXP di server ini.",
                    color=0x8B5CF6,
                )
            )
            return

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for r in board:
            rank_num = r["rank"]
            rank_badge = medals.get(rank_num, f"`#{rank_num}`")
            lines.append(
                f"{rank_badge} **{r['display_name']}** — **Lv. {r['level']}** (`{r['current_exp']}/{r['max_exp']} EXP` • `{r['total_messages']} akt`)"
            )
        emb = _make_embed(
            title=f"🏆 Top {len(board)} Leaderboard Server",
            description=(
                "\n".join(lines)
                + "\n\n✨ *Dapatkan EXP melalui Chat, Join Voice, Speak, Listening, Streaming, & Minigames!*"
            ),
            color=0x8B5CF6,
            category_label="Athenaa Server Leaderboard",
        )
        await interaction.response.send_message(embed=emb)

    @bot.tree.command(name="afk", description="Pasang status AFK di server ini")
    async def cmd_afk(interaction: discord.Interaction, alasan: str = "Sedang AFK") -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        leveling_service.set_afk(
            guild_id=guild_id,
            user_id=str(interaction.user.id),
            username=interaction.user.display_name,
            reason=alasan,
        )
        emb = _make_embed(
            title="💤 Status AFK Diaktifkan",
            description=(
                f"👤 **Anggota:** {interaction.user.mention}\n"
                f"💬 **Alasan:** {alasan}\n\n"
                f"*Bot akan memberi tahu siapa pun yang me-mention kamu dan mencabut AFK otomatis saat kamu kembali chat.*"
            ),
            color=0xF59E0B,
            category_label="Sistem Status AFK",
            thumbnail_url=interaction.user.display_avatar.url if interaction.user.display_avatar else "",
        )
        await interaction.response.send_message(embed=emb)

    # =========================================================================
    # Fun & Interactive Minigames Slash Commands (/kuis, /mathbattle, /suit, /8ball, /dadu)
    # =========================================================================
    @bot.tree.command(name="kuis", description="Mainkan kuis trivia interaktif untuk mahasiswa & pelajar (+25 EXP)")
    async def cmd_kuis(interaction: discord.Interaction) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        q = random.choice(TRIVIA_QUESTIONS)
        opts_text = "\n".join(f"**{opt}**" for opt in q["options"])
        emb = _make_embed(
            title=f"🧠 Kuis Trivia: {q['category']}",
            description=f"**{q['question']}**\n\n{opts_text}\n\n⏱️ *Klik tombol jawaban di bawah dalam 45 detik untuk meraih **+25 EXP**!*",
            color=0xEC4899,
            category_label="Athenaa Minigames • Trivia Kampus",
        )
        view = TriviaQuizView(q, guild_id)
        await interaction.response.send_message(embed=emb, view=view)

    @bot.tree.command(name="mathbattle", description="Tantangan hitung cepat matematika dengan hadiah +20 EXP")
    async def cmd_mathbattle(interaction: discord.Interaction) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        a = random.randint(12, 48)
        b = random.randint(6, 29)
        c = random.randint(2, 9)
        op_choice = random.choice(["+", "-", "*"])
        if op_choice == "+":
            expr = f"({a} × {c}) + {b}"
            ans = (a * c) + b
        elif op_choice == "-":
            expr = f"({a} × {c}) - {b}"
            ans = (a * c) - b
        else:
            expr = f"({a} + {b}) × {c}"
            ans = (a + b) * c

        wrongs = {ans + random.choice([-12, -6, -4, 4, 6, 10, 14]) for _ in range(10)}
        wrongs.discard(ans)
        options = [ans] + list(wrongs)[:3]
        while len(options) < 4:
            options.append(ans + len(options) * 3)
        random.shuffle(options)

        emb = _make_embed(
            title="⚡ Math Battle — Siapa Cepat Dia Dapat!",
            description=(
                f"Berapakah hasil dari operasi berikut?\n\n"
                f"# `{expr} = ?`\n\n"
                f"🏆 *Klik tombol jawaban yang benar untuk mendapatkan **+20 EXP**!*"
            ),
            color=0xEC4899,
            category_label="Athenaa Minigames • Math Battle",
        )
        view = MathBattleView(expr, ans, options, guild_id)
        await interaction.response.send_message(embed=emb, view=view)

    @bot.tree.command(name="suit", description="Mainkan Batu-Gunting-Kertas melawan Athenaa (+15 EXP jika menang)")
    async def cmd_suit(interaction: discord.Interaction, pilihan: str) -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        user_pick = pilihan.strip().lower()
        valid = {"batu": "🪨 Batu", "gunting": "✂️ Gunting", "kertas": "📄 Kertas"}
        if user_pick not in valid:
            await interaction.response.send_message(
                embed=_make_embed(
                    title="⚠️ Pilihan Suit Tidak Valid",
                    description="Pilih salah satu: `batu`, `gunting`, atau `kertas`.",
                    color=0xEF4444,
                ),
                ephemeral=True,
            )
            return

        bot_pick = random.choice(list(valid.keys()))
        wins = {("batu", "gunting"), ("gunting", "kertas"), ("kertas", "batu")}
        if user_pick == bot_pick:
            outcome = "🤝 **Hasil Seri!** Pikiran kita sejalan."
            color = 0xF59E0B
        elif (user_pick, bot_pick) in wins:
            _, lvl, c_exp, m_exp = leveling_service.process_voice_activity(
                guild_id=guild_id,
                user_id=str(interaction.user.id),
                username=interaction.user.name,
                display_name=interaction.user.display_name,
                activity_type="minigame",
                cooldown_seconds=10,
                exp_gain=15,
            )
            outcome = f"🎉 **Kamu Menang! (+15 EXP)** • Level **{lvl}** (`{c_exp}/{m_exp} EXP`)"
            color = 0xDC95FF
        else:
            outcome = "😄 **Athenaa Menang!** Coba lagi keberuntunganmu."
            color = 0xEC4899

        emb = _make_embed(
            title="✊✋✌️ Suit Batu-Gunting-Kertas",
            description=outcome,
            color=color,
            category_label="Athenaa Minigames",
        )
        emb.add_field(name=interaction.user.display_name, value=valid[user_pick], inline=True)
        emb.add_field(name="VS", value="⚡", inline=True)
        emb.add_field(name="Athenaa Bot", value=valid[bot_pick], inline=True)
        await interaction.response.send_message(embed=emb)

    @bot.tree.command(name="8ball", description="Tanyakan pertanyaan ke Kerang Ajaib Athenaa")
    async def cmd_8ball(interaction: discord.Interaction, pertanyaan: str) -> None:
        answers = [
            "✨ Pasti berhasil! Gas terus tanpa ragu.",
            "🟢 Sangat mungkin terjadi dalam waktu dekat.",
            "🔥 Tanda-tandanya sangat positif, lanjutkan!",
            "🤔 Coba fokus selesaikan tugas kuliah dulu, baru tanya lagi.",
            "⏳ Sabar sebentar, waktunya belum tepat.",
            "🎲 Peluangnya 50:50, pastikan kamu sudah siap.",
            "🛑 Sebaiknya pikirkan rencana cadangan (Plan B).",
        ]
        emb = _make_embed(
            title="🐚 Kerang Ajaib Athenaa",
            description=f"❓ **Pertanyaan:** *{pertanyaan}*\n\n🔮 **Jawaban:** **{random.choice(answers)}**",
            color=0xEC4899,
            category_label="Athenaa Fun Addon",
        )
        await interaction.response.send_message(embed=emb)

    @bot.tree.command(name="dadu", description="Lempar dadu keberuntungan (default 6 sisi, mendukung d20 / d100)")
    async def cmd_dadu(interaction: discord.Interaction, sisi: int = 6) -> None:
        max_sides = max(2, min(1000, sisi))
        rolled = random.randint(1, max_sides)
        emb = _make_embed(
            title=f"🎲 Lemparan Dadu d{max_sides}",
            description=f"**{interaction.user.display_name}** melempar dadu **{max_sides} sisi** dan mendapatkan angka:\n\n# 🎯 `{rolled}`",
            color=0xEC4899,
            category_label="Athenaa Minigames • Dice Roller",
        )
        await interaction.response.send_message(embed=emb)

    @bot.tree.command(name="invite", description="Dapatkan link invite resmi untuk mengundang Athenaa Bot ke server Discord")
    async def cmd_invite(interaction: discord.Interaction) -> None:
        client_id = str(getattr(bot.user, "id", "") or settings.discord_client_id or "").strip()
        if not client_id:
            await interaction.response.send_message(
                "⚠️ `DISCORD_CLIENT_ID` belum terdeteksi.",
                ephemeral=True,
            )
            return

        admin_invite = (
            f"https://discord.com/oauth2/authorize?client_id={client_id}"
            "&permissions=8&scope=bot%20applications.commands"
        )
        standard_invite = (
            f"https://discord.com/oauth2/authorize?client_id={client_id}"
            "&permissions=36793408&scope=bot%20applications.commands"
        )

        emb = _make_embed(
            title="🔗 Undang Athenaa Bot ke Server Discord",
            description=(
                "Pilih salah satu tautan di bawah untuk mengundang **Athenaa** beserta seluruh Slash Commands (`/play`, `/nowplaying`, `/tugas`, `/sync_waskita`, `/leaderboard`, dll.):\n\n"
                f"👑 **[Link Invite Full Akses (Administrator — Direkomendasikan)]({admin_invite})**\n"
                f"🎵 **[Link Invite Standar (Voice, Musik, Embed & Slash Commands)]({standard_invite})**\n\n"
                f"🌐 **Web Dashboard:** [{settings.web_base_url}]({settings.web_base_url})"
            ),
            color=0xDC95FF,
            category_label="Athenaa Bot Invite Link",
        )
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="👑 Invite Bot (Full Admin)",
                style=discord.ButtonStyle.link,
                url=admin_invite,
            )
        )
        view.add_item(
            discord.ui.Button(
                label="🎵 Invite Bot (Standar Musik & Voice)",
                style=discord.ButtonStyle.link,
                url=standard_invite,
            )
        )
        await interaction.response.send_message(embed=emb, view=view)

    @bot.tree.command(name="admin", description="Panel Admin Server (backup, sync, reset_voice)")
    async def cmd_admin(interaction: discord.Interaction, aksi: str = "backup") -> None:
        guild_id = str(interaction.guild_id or settings.main_guild_id)
        uid, uname, roles, is_admin, _ = _member_context(interaction)
        if not is_admin:
            await interaction.response.send_message(
                embed=_make_embed(
                    title="🔒 Khusus Admin Server",
                    description="Perintah `/admin` hanya dapat dijalankan oleh **Admin Server** (Administrator / Manage Server).",
                    color=0xEF4444,
                ),
                ephemeral=True,
            )
            return

        act = aksi.strip().lower()
        if act == "backup":
            res = await asyncio.to_thread(backup_service.create_consistent_backup, True)
            emb = _make_embed(
                title="💾 Backup SQLite Server Selesai",
                description=(
                    f"📦 **File:** `{Path(str(res.get('path', 'backup.enc'))).name}`\n"
                    f"📏 **Ukuran:** `{res.get('size_bytes', 0)} bytes`\n"
                    f"🔐 **Enkripsi:** `{'Aktif' if res.get('encrypted') else 'Standar'}`"
                ),
                color=0x10B981,
                category_label="Admin Server Hub",
            )
            await interaction.response.send_message(embed=emb, ephemeral=True)
        elif act == "sync":
            await interaction.response.defer(ephemeral=True)
            synced = await bot.tree.sync()
            emb = _make_embed(
                title="🔄 Slash Commands Disinkronkan",
                description=f"Berhasil menyinkronkan **{len(synced)}** global slash commands ke Discord.",
                color=0x38BDF8,
                category_label="Admin Server Hub",
            )
            await interaction.followup.send(embed=emb, ephemeral=True)
        else:
            st = queue_service.get_state(guild_id)
            st.host_user_id = ""
            st.host_username = ""
            await bot.apply_web_control(guild_id, "stop")
            emb = _make_embed(
                title="🛠️ Sesi Voice & Host Lock Direset",
                description=f"Sesi pemutaran dan Host Lock di server ini telah direset oleh Admin **{uname}**.",
                color=0xDC95FF,
                category_label="Admin Server Hub",
            )
            await interaction.response.send_message(embed=emb)

    bot.create_player_control_view = lambda gid: MusicPlayerControlView(gid)
    return bot