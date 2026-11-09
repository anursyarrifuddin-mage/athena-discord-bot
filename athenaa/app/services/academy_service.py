"""
Modul Akademik, Sinkronisasi Kalender Moodle (.ics), Google Classroom OAuth, dan Reminder 3 Tahap.
- Mem-parsing VEVENT dari file/URL kalender .ics tanpa duplikasi berdasarkan UID.
- Otomatis memblokir tugas yang sudah melewati tenggat waktu (deadline) agar tidak di-input ke database.
- Otomatis menghapus (DELETE) tugas yang sudah melewati tenggat waktu dari database SQLite.
- Sistem Reminder Persisten 3 Tahap (H-3 hari, H-6 jam, H-1 jam) yang tercatat di reminder_deliveries.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from app.config import settings
from app.database import DatabaseManager, db_manager
from app.security.validators import validate_external_url as validate_safe_external_url


@dataclass
class ParsedCalendarEvent:
    uid: str
    course_name: str
    title: str
    description: str
    deadline_iso: str
    url: str = ""


ICS_DATETIME_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?$")


def _get_jakarta_tz():
    try:
        return ZoneInfo("Asia/Jakarta")
    except Exception:
        return timezone(timedelta(hours=7))


def parse_deadline_datetime(deadline_iso: str) -> Optional[datetime]:
    """Mengonversi string ISO-8601 menjadi objek datetime timezone-aware."""
    raw = (deadline_iso or "").strip()
    if not raw:
        return None
    try:
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_get_jakarta_tz())
        return dt
    except Exception:
        return None


def is_deadline_expired(deadline_iso: str, now: Optional[datetime] = None) -> bool:
    """
    Mengembalikan True apabila waktu tenggat (deadline_iso) sudah terlewati (<= waktu sekarang)
    atau format tanggal tidak valid.
    """
    dt = parse_deadline_datetime(deadline_iso)
    if dt is None:
        return True
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return dt <= current


def parse_ics_datetime(raw_value: str, target_tz_name: str = "Asia/Jakarta") -> str:
    """Mengonversi nilai DTEND/DTSTART format iCalendar ke ISO-8601 pada zona waktu target."""
    val = raw_value.strip()
    if ":" in val:
        val = val.split(":", 1)[1].strip()
    match = ICS_DATETIME_RE.match(val)
    if not match:
        raise ValueError(f"Format waktu iCalendar tidak dikenali: {raw_value}")

    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour = int(match.group(4) or 23)
    minute = int(match.group(5) or 59)
    second = int(match.group(6) or 0)
    is_utc = bool(match.group(7))

    try:
        target_tz = ZoneInfo(target_tz_name)
    except Exception:
        target_tz = timezone(timedelta(hours=7))

    if is_utc:
        dt = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc).astimezone(target_tz)
    else:
        dt = datetime(year, month, day, hour, minute, second, tzinfo=target_tz)
    return dt.isoformat()


def is_submittable_or_due_task(
    summary: str,
    description: str = "",
    url: str = "",
    has_due_prop: bool = False,
    event_type: str = "",
) -> bool:
    """
    Memfilter event kalender Moodle/Waskita agar HANYA mengimpor tugas yang bisa di-turn in
    atau tempat mahasiswa dapat mengunggah file/jawaban (due date turn-in).
    """
    s = summary.strip().lower()
    d = description.strip().lower()
    u = url.strip().lower()
    ev_type = event_type.strip().lower()
    full_text = f"{s} {d}".strip()

    if not s:
        return False

    if any(
        mod_res in u
        for mod_res in (
            "/mod/resource/",
            "/mod/folder/",
            "/mod/page/",
            "/mod/url/",
            "/mod/book/",
            "/mod/label/",
        )
    ):
        return False

    if (
        s.endswith(" opens")
        or s.endswith(" is open")
        or " opens" in s
        or "dibuka pada" in s
        or "mulai dibuka" in s
        or "tersedia mulai" in s
        or ev_type in ("open", "opens")
    ) and not any(kw in full_text for kw in ("due", "closes", "berakhir", "deadline", "tenggat", "kumpul", "submit", "turn in")):
        return False

    if any(
        kw in s
        for kw in (
            "attendance",
            "presensi",
            "absensi",
            "daftar hadir",
        )
    ) or "/mod/attendance/" in u:
        if not any(kw in full_text for kw in ("tugas", "assign", "kumpul", "submit", "turn in", "laporan", "praktikum", "laprak", "kuis", "quiz", "ujian")):
            return False

    is_pure_module_or_slide = any(
        kw in s
        for kw in (
            "materi",
            "slide",
            "bahan ajar",
            "bahan kuliah",
            "silabus",
            "handout",
            "catatan kuliah",
            "buku ajar",
            "referensi",
            "bacaan",
            "rekaman perkuliahan",
            "video materi",
        )
    ) and not any(
        kw in full_text
        for kw in (
            "tugas",
            "assign",
            "assignment",
            "kumpul",
            "pengumpulan",
            "submit",
            "turn in",
            "upload",
            "unggah",
            "laporan",
            "praktikum",
            "laprak",
            "kuis",
            "quiz",
            "ujian",
            "uts",
            "uas",
            "project",
            "proyek",
            "tubes",
            "tugas besar",
        )
    )
    if is_pure_module_or_slide:
        return False

    if re.match(r"^(modul|pertemuan|bab|ch\.|chapter|sesi|unit)\s+\d+[\s:.-]*$", s):
        return False
    if re.match(r"^(modul|pertemuan|materi)\b", s) and not any(
        kw in full_text
        for kw in ("tugas", "kumpul", "submit", "turn in", "laporan", "laprak", "praktikum", "assign", "due", "deadline", "tenggat", "unggah", "upload")
    ):
        return False

    if any(
        mod_path in u
        for mod_path in (
            "/mod/assign/",
            "/mod/quiz/",
            "/mod/workshop/",
            "/mod/turnitintool",
            "/mod/turnitintooltwo/",
        )
    ):
        return True

    if any(
        kw in full_text
        for kw in (
            "is due",
            "due",
            "closes",
            "tenggat",
            "deadline",
            "tugas",
            "assign",
            "assignment",
            "kumpul",
            "pengumpulan",
            "submit",
            "submission",
            "turn in",
            "unggah tugas",
            "upload tugas",
            "upload file",
            "laporan praktikum",
            "laprak",
            "laporan",
            "praktikum",
            "kuis",
            "quiz",
            "ujian",
            "uts",
            "uas",
            "project",
            "proyek",
            "tubes",
            "tugas besar",
            "makalah",
            "responsi",
            "lembar kerja",
        )
    ):
        return True

    return False


def parse_moodle_ics_content(
    ics_text: str,
    target_tz_name: str = "Asia/Jakarta",
    now: Optional[datetime] = None,
) -> List[ParsedCalendarEvent]:
    """
    Mem-parsing isi kalender .ics Moodle/Waskita dan HANYA mengekstrak VEVENT tugas
    yang dapat dikumpulkan (turn-in) DAN belum melewati waktu tenggat (deadline > now).
    """
    unfolded = re.sub(r"\r?\n[ \t]", "", ics_text)
    events: List[ParsedCalendarEvent] = []
    in_event = False
    fields: Dict[str, str] = {}
    current = now or datetime.now(timezone.utc)

    for raw_line in unfolded.splitlines():
        line = raw_line.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            fields = {}
            continue
        if line == "END:VEVENT":
            in_event = False
            uid = fields.get("UID", "").strip()
            summary = fields.get("SUMMARY", "").strip()
            description = fields.get("DESCRIPTION", "").replace("\\n", "\n").strip()
            url = fields.get("URL", "").strip()
            has_due = bool(fields.get("DUE") or fields.get("DTEND"))
            dt_raw = fields.get("DUE") or fields.get("DTEND") or fields.get("DTSTART") or ""
            if uid and summary and dt_raw:
                if not is_submittable_or_due_task(
                    summary=summary,
                    description=description,
                    url=url,
                    has_due_prop=has_due,
                ):
                    continue
                try:
                    deadline_iso = parse_ics_datetime(dt_raw, target_tz_name)
                    # JANGAN menginput tugas yang sudah melewati tenggat waktu (deadline)!
                    if is_deadline_expired(deadline_iso, now=current):
                        continue

                    course_name = fields.get("CATEGORIES", "").strip()
                    if not course_name and "[" in summary and "]" in summary:
                        course_name = summary[summary.find("[") + 1 : summary.find("]")].strip()
                    if not course_name:
                        course_name = "Moodle / Waskita"
                    clean_title = re.sub(r"^\[[^\]]+\]\s*", "", summary)
                    clean_title = re.sub(
                        r"\s+(is due|closes|berakhir|jatuh tempo)$",
                        "",
                        clean_title,
                        flags=re.IGNORECASE,
                    ).strip()
                    if not clean_title:
                        clean_title = summary.replace(" is due", "").strip()
                    events.append(
                        ParsedCalendarEvent(
                            uid=uid,
                            course_name=course_name,
                            title=clean_title,
                            description=description,
                            deadline_iso=deadline_iso,
                            url=url,
                        )
                    )
                except ValueError:
                    pass
            continue

        if in_event and ":" in line:
            key_part, val_part = line.split(":", 1)
            base_key = key_part.split(";", 1)[0].upper()
            fields[base_key] = val_part

    return events


@dataclass
class TaskRecord:
    task_id: str
    guild_id: str
    external_uid: str
    course_name: str
    title: str
    description: str
    source_type: str
    deadline_iso: str
    timezone: str
    source_url: str
    is_completed: int
    completed_by: str
    completed_at: str
    created_by: str
    last_synced_at: str
    updated_at: str


DEFAULT_MOODLE_ICS_SAMPLE = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Moodle Pty Ltd//NONSGML Moodle Version 2026042000//EN
BEGIN:VEVENT
UID:moodle-event-9001@elearning.ac.id
SUMMARY:[IF3130 Jaringan Komputer] Laporan Praktikum Analisis Paket TCP/UDP & Wireshark is due
DESCRIPTION:Unggah laporan PDF hasil capture Wireshark beserta analisis three-way handshake.
CATEGORIES:IF3130 Jaringan Komputer
DTEND:20261110T165900Z
URL:https://elearning.ac.id/mod/assign/view.php?id=9001
END:VEVENT
BEGIN:VEVENT
UID:moodle-event-9002@elearning.ac.id
SUMMARY:[IF2240 Basis Data] Perancangan Skema Normalisasi BCNF & Indexing SQLite is due
DESCRIPTION:Sertakan DDL SQL dan analisis query plan EXPLAIN QUERY PLAN.
CATEGORIES:IF2240 Basis Data
DTEND:20261114T165900Z
URL:https://elearning.ac.id/mod/assign/view.php?id=9002
END:VEVENT
END:VCALENDAR"""


class AcademyService:
    """Layanan manajemen tugas akademik, sinkronisasi .ics Waskita/Moodle, dan auto-purge tugas lewat deadline."""

    # Purge interval: max 1x per 5 minutes per guild
    PURGE_INTERVAL_SEC = 300

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or db_manager
        self._last_purge: Dict[str, float] = {}  # guild_id -> timestamp

    def _maybe_purge(self, guild_id: str, now: Optional[datetime] = None) -> int:
        """Only run purge if enough time has passed since last purge for this guild."""
        current_time = time.time()
        last_purge_time = self._last_purge.get(guild_id, 0)
        if current_time - last_purge_time < self.PURGE_INTERVAL_SEC:
            return 0
        self._last_purge[guild_id] = current_time
        return self.purge_expired_tasks(guild_id, now=now)

    def is_main_guild(self, guild_id: str) -> bool:
        return str(guild_id or "").strip() == str(settings.main_guild_id or "1428666546942902294").strip()

    def ensure_guild_exists(self, guild_id: str, guild_name: Optional[str] = None) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        gid = str(guild_id or "").strip()
        is_main = self.is_main_guild(gid)
        clean_name = (guild_name or "").strip()
        default_name = "TK1GACORKINK" if is_main else (clean_name or f"Discord Server {gid}")
        default_task_ch = settings.task_reminder_channel_id if is_main else ""
        default_dj_role = settings.dj_role_id if is_main else ""

        with self.db.transaction() as conn:
            if clean_name:
                conn.execute(
                    """
                    INSERT INTO guild_settings (guild_id, guild_name, task_channel_id, dj_role_id, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        guild_name = excluded.guild_name,
                        updated_at = excluded.updated_at
                    """,
                    (gid, clean_name, default_task_ch, default_dj_role, now_iso),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO guild_settings (guild_id, guild_name, task_channel_id, dj_role_id, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO NOTHING
                    """,
                    (gid, default_name, default_task_ch, default_dj_role, now_iso),
                )

    def remove_guild(self, guild_id: str) -> None:
        """Menghapus entri guild_settings saat bot dikeluarkan dari server Discord (kecuali main_guild_id)."""
        if str(guild_id) == str(settings.main_guild_id or ""):
            return
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM guild_settings WHERE guild_id = ?", (str(guild_id),))

    def purge_expired_tasks(
        self,
        guild_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> int:
        """
        Menghapus secara permanen dari database semua tugas yang sudah melewati tenggat waktu (deadline <= now),
        beserta entri reminder_deliveries terkait agar database selalu bersih.
        """
        current = now or datetime.now(timezone.utc)
        expired_ids: List[str] = []

        with self.db.transaction() as conn:
            if guild_id:
                rows = conn.execute(
                    "SELECT task_id, deadline_iso FROM tasks WHERE guild_id = ?",
                    (str(guild_id),),
                ).fetchall()
            else:
                rows = conn.execute("SELECT task_id, deadline_iso FROM tasks").fetchall()

            for r in rows:
                if is_deadline_expired(str(r["deadline_iso"] or ""), now=current):
                    expired_ids.append(str(r["task_id"]))

            for tid in expired_ids:
                conn.execute("DELETE FROM reminder_deliveries WHERE task_id = ?", (tid,))
                conn.execute("DELETE FROM tasks WHERE task_id = ?", (tid,))

        return len(expired_ids)

    def _row_to_task(self, row) -> TaskRecord:
        return TaskRecord(
            task_id=str(row["task_id"]),
            guild_id=str(row["guild_id"]),
            external_uid=str(row["external_uid"] or ""),
            course_name=str(row["course_name"]),
            title=str(row["title"]),
            description=str(row["description"] or ""),
            source_type=str(row["source_type"] or "manual"),
            deadline_iso=str(row["deadline_iso"]),
            timezone=str(row["timezone"] or "Asia/Jakarta"),
            source_url=str(row["source_url"] or ""),
            is_completed=int(row["is_completed"] or 0),
            completed_by=str(row["completed_by"] or ""),
            completed_at=str(row["completed_at"] or ""),
            created_by=str(row["created_by"] or "Discord User"),
            last_synced_at=str(row["last_synced_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )

    def list_tasks(self, guild_id: str, include_completed: bool = True) -> List[TaskRecord]:
        self.ensure_guild_exists(guild_id)
        # Hapus otomatis semua tugas yang sudah melewati deadline sebelum mengambil daftar
        self._maybe_purge(guild_id)

        with self.db.transaction() as conn:
            if include_completed:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE guild_id = ? ORDER BY is_completed ASC, deadline_iso ASC",
                    (guild_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE guild_id = ? AND is_completed = 0 ORDER BY deadline_iso ASC",
                    (guild_id,),
                ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def create_task(
        self,
        guild_id: str,
        course_name: str,
        title: str,
        deadline_iso: str,
        created_by: str = "Discord User",
        description: str = "",
        source_url: str = "",
        timezone_name: str = "Asia/Jakarta",
    ) -> TaskRecord:
        self.ensure_guild_exists(guild_id)
        self._maybe_purge(guild_id)

        task_id = f"tsk-{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, guild_id, external_uid, course_name, title, description,
                    source_type, deadline_iso, timezone, source_url, is_completed,
                    created_by, last_synced_at, updated_at
                ) VALUES (?, ?, '', ?, ?, ?, 'manual', ?, ?, ?, 0, ?, '', ?)
                """,
                (
                    task_id,
                    guild_id,
                    course_name.strip() or "Umum",
                    title.strip(),
                    description.strip(),
                    deadline_iso,
                    timezone_name,
                    source_url.strip(),
                    created_by.strip() or "Discord User",
                    now_iso,
                ),
            )
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            return self._row_to_task(row)

    def set_task_completion(
        self,
        guild_id: str,
        task_id: str,
        completed: bool,
        actor_name: str = "User",
    ) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE tasks
                SET is_completed = ?,
                    completed_by = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE task_id = ? AND guild_id = ?
                """,
                (
                    1 if completed else 0,
                    actor_name if completed else "",
                    now_iso if completed else "",
                    now_iso,
                    task_id,
                    guild_id,
                ),
            )
            return cur.rowcount > 0

    def toggle_task(self, task_id: str, actor_name: str = "User") -> Optional[TaskRecord]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return None
            new_state = 0 if int(row["is_completed"] or 0) == 1 else 1
            conn.execute(
                """
                UPDATE tasks
                SET is_completed = ?,
                    completed_by = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    new_state,
                    actor_name if new_state == 1 else "",
                    now_iso if new_state == 1 else "",
                    now_iso,
                    task_id,
                ),
            )
            updated = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            return self._row_to_task(updated) if updated else None

    def delete_task(self, guild_id: str, task_id: str) -> bool:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM reminder_deliveries WHERE task_id = ?", (task_id,))
            if guild_id:
                cur = conn.execute("DELETE FROM tasks WHERE task_id = ? AND guild_id = ?", (task_id, guild_id))
            else:
                cur = conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            return cur.rowcount > 0

    def delete_attachment(self, guild_id: str, attachment_id: str) -> Optional[Dict[str, object]]:
        """Menghapus modul/lampiran dari tabel task_attachments beserta file fisiknya di direktori modules."""
        att_id = (attachment_id or "").strip()
        gid = (guild_id or "").strip()
        if not att_id:
            return None

        with self.db.transaction() as conn:
            if gid:
                row = conn.execute(
                    "SELECT * FROM task_attachments WHERE attachment_id = ? AND guild_id = ?",
                    (att_id, gid),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM task_attachments WHERE attachment_id = ?",
                    (att_id,),
                ).fetchone()

            if not row:
                return None

            row_data = dict(row)
            conn.execute("DELETE FROM task_attachments WHERE attachment_id = ?", (att_id,))

        stored_name = str(row_data.get("stored_filename") or "").strip()
        if stored_name and "/" not in stored_name and "\\" not in stored_name:
            candidate_dirs = [Path("modules"), Path("data/modules")]
            if getattr(settings, "modules_dir", None):
                candidate_dirs.insert(0, Path(settings.modules_dir))
            for d in candidate_dirs:
                try:
                    fp = d / stored_name
                    if fp.is_file():
                        fp.unlink(missing_ok=True)
                except Exception:
                    pass

        return row_data

    @staticmethod
    def get_moodle_env_status() -> Dict[str, object]:
        masked_user = ""
        if settings.moodle_username:
            u = settings.moodle_username
            masked_user = u[:2] + "***" + u[-1:] if len(u) > 3 else u[0] + "***"
        return {
            "env_moodle_configured": bool(
                settings.moodle_ical_url or (settings.moodle_username and settings.moodle_password)
            ),
            "moodle_base_url": settings.moodle_base_url or "https://lms.kampus.ac.id",
            "has_ical_url": bool(settings.moodle_ical_url),
            "moodle_ical_url_preview": (
                settings.moodle_ical_url[:48] + "..."
                if len(settings.moodle_ical_url) > 48
                else settings.moodle_ical_url
            ),
            "has_credentials": bool(settings.moodle_username and settings.moodle_password),
            "masked_username": masked_user,
            "auto_sync_interval_seconds": 3600,
            "daily_reminder_wib": "00:01",
            "task_reminder_channel_id": settings.task_reminder_channel_id,
        }

    def get_guild_saved_ical_url(self, guild_id: str) -> str:
        try:
            with self.db.transaction() as conn:
                row = conn.execute(
                    "SELECT moodle_ics_url_encrypted FROM guild_settings WHERE guild_id = ?",
                    (guild_id,),
                ).fetchone()
            raw_val = str(row["moodle_ics_url_encrypted"] or "").strip() if row else ""
            if not raw_val:
                return ""
            if raw_val.startswith(("http://", "https://")):
                return raw_val
            from app.security.validators import decrypt_secret

            dec = decrypt_secret(raw_val).strip()
            return dec if dec.startswith(("http://", "https://")) else ""
        except Exception:
            return ""

    def fetch_moodle_ics_or_login(
        self,
        ical_url: str = "",
        base_url: str = "",
        username: str = "",
        password: str = "",
        allow_sample_fallback: bool = True,
    ) -> Tuple[str, str]:
        target_ical = (ical_url or "").strip()
        target_base = (base_url or "").strip().rstrip("/")
        target_user = (username or "").strip()
        target_pass = (password or "").strip()

        if target_ical.startswith(("http://", "https://")):
            ok, reason = validate_safe_external_url(target_ical)
            if not ok:
                raise ValueError(f"URL iCal Moodle ditolak oleh filter keamanan SSRF: {reason}")
            try:
                req = urllib.request.Request(
                    target_ical,
                    headers={"User-Agent": "AthenaaAcademicSync/1.0"},
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                if "BEGIN:VCALENDAR" in raw:
                    return raw, "Waskita / Moodle iCal (.ics)"
            except Exception:
                pass

        if target_base.startswith(("http://", "https://")) and target_user and target_pass:
            ok, reason = validate_safe_external_url(target_base)
            if not ok:
                raise ValueError(f"MOODLE_BASE_URL ditolak oleh filter keamanan SSRF: {reason}")
            try:
                token_url = f"{target_base}/login/token.php"
                form = urllib.parse.urlencode(
                    {
                        "username": target_user,
                        "password": target_pass,
                        "service": "moodle_mobile_app",
                    }
                ).encode("utf-8")
                req = urllib.request.Request(
                    token_url,
                    data=form,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": "AthenaaAcademicSync/1.0",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    tok_data = json.loads(resp.read().decode("utf-8", errors="replace"))
                wstoken = str(tok_data.get("token") or "").strip()
                if wstoken:
                    ws_url = (
                        f"{target_base}/webservice/rest/server.php?"
                        + urllib.parse.urlencode(
                            {
                                "wstoken": wstoken,
                                "wsfunction": "core_calendar_get_calendar_upcoming_view",
                                "moodlewsrestformat": "json",
                            }
                        )
                    )
                    with urllib.request.urlopen(ws_url, timeout=12) as ws_resp:
                        cal_data = json.loads(ws_resp.read().decode("utf-8", errors="replace"))
                    events = cal_data.get("events") or []
                    if isinstance(events, list) and events:
                        now_ts = int(datetime.now(timezone.utc).timestamp())
                        lines = [
                            "BEGIN:VCALENDAR",
                            "VERSION:2.0",
                            "PRODID:-//Athenaa Waskita Moodle Login Sync//ID",
                        ]
                        for ev in events:
                            ts = int(ev.get("timestart") or 0)
                            # Abaikan tugas dari Waskita WebService yang sudah melewati tenggat waktu
                            if ts <= now_ts:
                                continue

                            ev_type = str(ev.get("eventtype") or "").strip().lower()
                            modulename = str(ev.get("modulename") or "").strip().lower()
                            course_obj = ev.get("course") or {}
                            course_name = str(course_obj.get("fullname") or "Moodle / Waskita")
                            name = str(ev.get("name") or "Tugas Kuliah")
                            desc = re.sub(r"<[^>]+>", "", str(ev.get("description") or "")).strip()
                            url = str(ev.get("url") or f"{target_base}/calendar/view.php")
                            if not is_submittable_or_due_task(
                                summary=f"[{course_name}] {name}",
                                description=desc,
                                url=url or (f"/mod/{modulename}/" if modulename else ""),
                                has_due_prop=ev_type in ("due", "close", "expectcompletionon", "gradingdue"),
                                event_type=ev_type,
                            ):
                                continue
                            uid = f"moodle-ws-{ev.get('id', uuid.uuid4().hex[:8])}@moodle"
                            dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                            lines.extend(
                                [
                                    "BEGIN:VEVENT",
                                    f"UID:{uid}",
                                    f"SUMMARY:[{course_name}] {name}",
                                    f"DESCRIPTION:{desc}",
                                    f"CATEGORIES:{course_name}",
                                    f"DTEND:{dt_str}",
                                    f"URL:{url}",
                                    "END:VEVENT",
                                ]
                            )
                        lines.append("END:VCALENDAR")
                        return "\r\n".join(lines), f"Waskita / Moodle Login ({target_user})"
            except Exception:
                pass

        if not allow_sample_fallback:
            return "", "Tidak ada sumber Waskita/Moodle aktif"

        return DEFAULT_MOODLE_ICS_SAMPLE, (
            f"Moodle Sync ({target_user or 'Kalender .ics'})"
            if (target_user or target_ical)
            else "Kalender Moodle (.ics)"
        )

    def sync_moodle_ics_content(
        self,
        guild_id: str,
        ics_content: str = "",
        actor_id: str = "Moodle Sync",
        ical_url: str = "",
        moodle_base_url: str = "",
        moodle_username: str = "",
        moodle_password: str = "",
        allow_sample_fallback: bool = False,
    ) -> Dict[str, object]:
        # Bersihkan tugas yang sudah lewat deadline sebelum sinkronisasi
        purged_count = self._maybe_purge(guild_id)

        is_main = self.is_main_guild(guild_id)
        saved_db_ical = self.get_guild_saved_ical_url(guild_id)

        effective_ical = (
            ical_url
            or saved_db_ical
            or (settings.moodle_ical_url if is_main else "")
        ).strip()
        effective_base = (moodle_base_url or (settings.moodle_base_url if is_main else "")).strip()
        effective_user = (moodle_username or (settings.moodle_username if is_main else "")).strip()
        effective_pass = (moodle_password or (settings.moodle_password if is_main else "")).strip()

        if ics_content.strip():
            payload = ics_content.strip()
            source_used = "Konten .ics Langsung"
        elif not is_main and not effective_ical and not (effective_user and effective_pass):
            return {
                "inserted": 0,
                "updated": 0,
                "purged_expired": purged_count,
                "source_used": "Belum dikonfigurasi di database server ini",
                "moodle_env": {
                    **self.get_moodle_env_status(),
                    "env_moodle_configured": bool(saved_db_ical),
                    "has_ical_url": bool(saved_db_ical),
                },
            }
        else:
            payload, source_used = self.fetch_moodle_ics_or_login(
                ical_url=effective_ical,
                base_url=effective_base,
                username=effective_user,
                password=effective_pass,
                allow_sample_fallback=(allow_sample_fallback if is_main else False),
            )
        if not payload.strip():
            return {
                "inserted": 0,
                "updated": 0,
                "purged_expired": purged_count,
                "source_used": source_used,
                "moodle_env": self.get_moodle_env_status() if is_main else {
                    **self.get_moodle_env_status(),
                    "env_moodle_configured": bool(saved_db_ical),
                    "has_ical_url": bool(saved_db_ical),
                },
            }
        inserted, updated = self.sync_ics_events(
            guild_id=guild_id,
            ics_text=payload,
            timezone_name="Asia/Jakarta",
            actor_id=actor_id,
        )
        return {
            "inserted": inserted,
            "updated": updated,
            "purged_expired": purged_count,
            "source_used": source_used,
            "moodle_env": self.get_moodle_env_status() if is_main else {
                **self.get_moodle_env_status(),
                "env_moodle_configured": bool(saved_db_ical),
                "has_ical_url": bool(saved_db_ical),
            },
        }

    def sync_ics_events(
        self,
        guild_id: str,
        ics_text: str,
        timezone_name: str = "Asia/Jakarta",
        actor_id: str = "system",
    ) -> Tuple[int, int]:
        """
        Menyinkronkan daftar VEVENT ke tabel tasks tanpa duplikasi (berdasarkan guild_id + external_uid).
        - Tugas yang sudah lewat deadline langsung dihapus dari DB dan tidak pernah di-input kembali.
        OPTIMIZED: Bulk fetch existing tasks to avoid N+1 queries.
        """
        self.ensure_guild_exists(guild_id)
        current_dt = datetime.now(timezone.utc)
        self._maybe_purge(guild_id, now=current_dt)

        parsed = parse_moodle_ics_content(ics_text, timezone_name, now=current_dt)
        now_iso = current_dt.isoformat()
        inserted = 0
        updated = 0

        # OPTIMIZATION: Bulk fetch all existing external_uids in one query
        existing_tasks = {}
        with self.db.transaction() as conn:
            if parsed:
                uids = [ev.uid for ev in parsed]
                placeholders = ",".join("?" * len(uids))
                rows = conn.execute(
                    f"SELECT task_id, external_uid, deadline_iso, title, description FROM tasks WHERE guild_id = ? AND external_uid IN ({placeholders})",
                    (guild_id, *uids),
                ).fetchall()
                existing_tasks = {row["external_uid"]: row for row in rows}

            for ev in parsed:
                # Double check: jika sudah lewat deadline, pastikan terhapus dari DB dan jangan di-insert
                if is_deadline_expired(ev.deadline_iso, now=current_dt):
                    conn.execute(
                        "DELETE FROM tasks WHERE guild_id = ? AND external_uid = ?",
                        (guild_id, ev.uid),
                    )
                    continue

                existing = existing_tasks.get(ev.uid)

                if existing is None:
                    task_id = f"tsk-{uuid.uuid4().hex[:10]}"
                    conn.execute(
                        """
                        INSERT INTO tasks (
                            task_id, guild_id, external_uid, course_name, title, description,
                            source_type, deadline_iso, timezone, source_url, is_completed,
                            created_by, last_synced_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, 'moodle_ics', ?, ?, ?, 0, ?, ?, ?)
                        """,
                        (
                            task_id,
                            guild_id,
                            ev.uid,
                            ev.course_name,
                            ev.title,
                            ev.description,
                            ev.deadline_iso,
                            timezone_name,
                            ev.url,
                            actor_id,
                            now_iso,
                            now_iso,
                        ),
                    )
                    inserted += 1
                else:
                    conn.execute(
                        """
                        UPDATE tasks
                        SET course_name = ?, title = ?, description = ?, deadline_iso = ?,
                            source_url = CASE WHEN ? != '' THEN ? ELSE source_url END,
                            last_synced_at = ?, updated_at = ?
                        WHERE task_id = ?
                        """,
                        (
                            ev.course_name,
                            ev.title,
                            ev.description,
                            ev.deadline_iso,
                            ev.url,
                            ev.url,
                            now_iso,
                            now_iso,
                            existing["task_id"],
                        ),
                    )
                    updated += 1

            conn.execute(
                "UPDATE guild_settings SET moodle_last_sync = ?, updated_at = ? WHERE guild_id = ?",
                (now_iso, now_iso, guild_id),
            )

        return inserted, updated

    def get_active_tasks_for_daily_reminder(
        self,
        guild_id: str,
        now: Optional[datetime] = None,
    ) -> List[TaskRecord]:
        """
        Menghapus seluruh tugas yang sudah lewat deadline dari DB, lalu mengambil tugas aktif (is_completed=0).
        """
        current = now or datetime.now(timezone.utc)
        self._maybe_purge(guild_id, now=current)

        all_pending = self.list_tasks(guild_id, include_completed=False)
        active_tasks: List[TaskRecord] = []
        for t in all_pending:
            if not is_deadline_expired(t.deadline_iso, now=current):
                active_tasks.append(t)
        return active_tasks

    def filter_unsent_daily_reminder_tasks(
        self,
        guild_id: str,
        date_wib_str: str,
        now: Optional[datetime] = None,
    ) -> List[TaskRecord]:
        stage = f"DAILY-00:01-{date_wib_str}"
        candidates = self.get_active_tasks_for_daily_reminder(guild_id, now=now)
        unsent: List[TaskRecord] = []
        with self.db.transaction() as conn:
            for t in candidates:
                row = conn.execute(
                    "SELECT 1 FROM reminder_deliveries WHERE task_id = ? AND stage = ?",
                    (t.task_id, stage),
                ).fetchone()
                if not row:
                    unsent.append(t)
        return unsent

    def mark_daily_reminder_sent(
        self,
        guild_id: str,
        task_ids: List[str],
        channel_id: str,
        date_wib_str: str,
    ) -> None:
        stage = f"DAILY-00:01-{date_wib_str}"
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            for tid in task_ids:
                delivery_id = f"rem-{uuid.uuid4().hex[:10]}"
                conn.execute(
                    """
                    INSERT OR IGNORE INTO reminder_deliveries (
                        delivery_id, task_id, guild_id, stage, delivered_at, channel_id, status
                    ) VALUES (?, ?, ?, ?, ?, ?, 'sent')
                    """,
                    (delivery_id, tid, guild_id, stage, now_iso, str(channel_id)),
                )

    def evaluate_due_reminders(
        self,
        guild_id: str,
        now: Optional[datetime] = None,
        days_before: int = 3,
    ) -> List[Dict[str, str]]:
        """
        Mengevaluasi pengingat 3 tahap (H-3d, H-6h, H-1h).
        Otomatis menghapus dari database tugas yang sudah melewati waktu deadline.
        """
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)

        # Bersihkan tugas lewat deadline dari DB terlebih dahulu
        self._maybe_purge(guild_id, now=current)

        deliveries_to_send: List[Dict[str, str]] = []

        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT task_id, guild_id, course_name, title, deadline_iso, source_url, is_completed
                FROM tasks
                WHERE guild_id = ? AND is_completed = 0
                """,
                (guild_id,),
            ).fetchall()

            for row in rows:
                deadline = parse_deadline_datetime(str(row["deadline_iso"] or ""))
                if deadline is None or deadline <= current:
                    conn.execute("DELETE FROM reminder_deliveries WHERE task_id = ?", (row["task_id"],))
                    conn.execute("DELETE FROM tasks WHERE task_id = ?", (row["task_id"],))
                    continue

                remaining = deadline - current
                rem_hours = remaining.total_seconds() / 3600.0

                stage: Optional[str] = None
                if rem_hours <= 1.0:
                    stage = "H-1h"
                elif rem_hours <= 6.0:
                    stage = "H-6h"
                elif rem_hours <= (days_before * 24.0):
                    stage = f"H-{days_before}d"

                if not stage:
                    continue

                already_sent = conn.execute(
                    "SELECT 1 FROM reminder_deliveries WHERE task_id = ? AND stage = ?",
                    (row["task_id"], stage),
                ).fetchone()

                if already_sent:
                    continue

                delivery_id = f"rem-{uuid.uuid4().hex[:10]}"
                conn.execute(
                    """
                    INSERT INTO reminder_deliveries (
                        delivery_id, task_id, guild_id, stage, delivered_at, channel_id, status
                    ) VALUES (?, ?, ?, ?, ?, ?, 'sent')
                    """,
                    (
                        delivery_id,
                        row["task_id"],
                        guild_id,
                        stage,
                        current.isoformat(),
                        "task-channel",
                    ),
                )
                deliveries_to_send.append(
                    {
                        "delivery_id": delivery_id,
                        "task_id": row["task_id"],
                        "course_name": row["course_name"],
                        "title": row["title"],
                        "deadline_iso": row["deadline_iso"],
                        "stage": stage,
                    }
                )

        return deliveries_to_send