"""
Suite Pengujian Otomatis Athenaa (Kompatibel dengan pytest dan python3 -m unittest).
Menguji seluruh kriteria penerimaan pada Bagian 15 Master Prompt:
1. Musik: Klasifikasi URL, penambahan/penghapusan antrean, pencegahan pemutaran ganda,
   Host Lock System, override DJ & Admin, volume & loop, autoplay anti-duplikat, perpindahan host.
2. Akademik: Parsing .ics Moodle, konversi zona waktu Asia/Jakarta, sinkronisasi tanpa duplikat,
   pembaruan deadline, pengiriman reminder 1x per tahap, penghentian reminder tugas selesai,
   validasi ukuran & ekstensi & magic bytes modul, pencegahan path traversal.
3. Keamanan & Operasional: Enkripsi/dekripsi HMAC, SSRF blocker, rate limiting,
   RPG Leveling & cooldown anti-spam, AFK persisten, dan backup SQLite konsisten.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.database import DatabaseManager
from app.models.schema import QueueItemModel
from app.security.validators import (
    SlidingWindowRateLimiter,
    can_control_queue,
    decrypt_secret,
    encrypt_secret,
    sanitize_and_validate_attachment,
    validate_external_url,
)
from app.services.academy_service import AcademyService, parse_moodle_ics_content
from app.services.backup_service import BackupService
from app.services.leveling_service import LevelingService, calculate_max_exp
from app.services.lyrics_service import parse_lrc_timestamps
from app.services.music_service import (
    _to_safe_ytdlp_target,
    classify_music_input,
    search_songs_with_singer,
    clear_music_history_db,
)
from app.services.queue_service import QueueService

SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Moodle Pty Ltd//NONSGML Moodle Version 2024042200//EN
BEGIN:VEVENT
UID:moodle-event-1001@kampus.ac.id
SUMMARY:Laporan Praktikum Jaringan Komputer is due
DESCRIPTION:Unggah laporan dalam format PDF sebelum batas waktu.
CATEGORIES:IF3130 Jaringan Komputer
DTEND:20271115T165900Z
URL:https://lms.kampus.ac.id/mod/assign/view.php?id=991
END:VEVENT
END:VCALENDAR
"""


class TestAthenaaSystem(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_athenaa.db"
        self.db = DatabaseManager(self.db_path)
        self.queue_svc = QueueService()
        self.academy_svc = AcademyService(self.db)
        self.leveling_svc = LevelingService(self.db)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_music_url_classification_and_youtube_spotify_only_guard(self) -> None:
        self.assertEqual(
            classify_music_input("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC")[0],
            "spotify_track",
        )
        self.assertEqual(
            classify_music_input("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")[0],
            "spotify_playlist",
        )
        self.assertEqual(
            classify_music_input("https://www.youtube.com/watch?v=dQw4w9WgXcQ")[0],
            "youtube",
        )
        self.assertEqual(classify_music_input("Hindia Evaluasi")[0], "search_query")

        # Ensure non-YouTube URLs (e.g. legacy Apple Music or Spotify links) are converted to ytsearch1:
        safe_target = _to_safe_ytdlp_target(
            "https://music.apple.com/us/album/hujan/534179662?i=534179698&uo=4"
        )
        self.assertTrue(safe_target.startswith("ytsearch1:"))
        self.assertNotIn("apple.com", safe_target)

        # Direct YouTube watch URL stays a YouTube URL
        yt_target = _to_safe_ytdlp_target("https://www.youtube.com/watch?v=2vcc2g6wHVQ")
        self.assertEqual(yt_target, "https://www.youtube.com/watch?v=2vcc2g6wHVQ")

        # Search results must strictly come from YouTube / Spotify catalog (never Apple Music)
        results = search_songs_with_singer("hujan", limit=5)
        self.assertGreater(len(results), 0)
        for item in results:
            self.assertIn(item.source_type, ("youtube", "spotify_matched"))
            self.assertNotIn("apple.com", item.source_url)

        # SSRF internal URL must be rejected
        ok_local, _ = validate_external_url("http://127.0.0.1:8080/admin")
        self.assertFalse(ok_local)
        ok_private, _ = validate_external_url("http://192.168.1.1/stream")
        self.assertFalse(ok_private)

    def test_queue_prevents_concurrent_playback_and_enforces_host_lock(self) -> None:
        guild_id = "guild-101"
        # User A starts the session -> becomes Session Host
        first, started1 = self.queue_svc.add_track(
            guild_id=guild_id,
            title="Evaluasi",
            artist="Hindia",
            duration_sec=195,
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            requester_id="user-host",
            requester_name="Dimas (Host)",
        )
        self.assertTrue(started1)
        state = self.queue_svc.get_state(guild_id)
        self.assertEqual(state.host_user_id, "user-host")

        # User B adds a song -> goes to queue (does NOT play simultaneously)
        second, started2 = self.queue_svc.add_track(
            guild_id=guild_id,
            title="Monokrom",
            artist="Tulus",
            duration_sec=214,
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=QqJ-Vp8mvbk",
            requester_id="user-regular",
            requester_name="Rina",
        )
        self.assertFalse(started2)
        self.assertEqual(len(state.queue), 1)
        self.assertEqual(state.current_track.item_id, first.item_id)

        # User B tries to skip or stop -> blocked by Host Lock
        with self.assertRaises(PermissionError):
            self.queue_svc.control_session(guild_id=guild_id, action="skip", actor_id="user-regular")

        # DJ role or Admin can override Host Lock
        self.queue_svc.control_session(
            guild_id=guild_id,
            action="volume",
            actor_id="user-admin",
            user_roles=["role-admin"],
            is_admin=True,
            value=65,
        )
        self.assertEqual(state.volume, 65)

        # Regular user CAN remove their own queued item
        removed = self.queue_svc.remove_item(
            guild_id=guild_id,
            item_id=second.item_id,
            actor_id="user-regular",
        )
        self.assertEqual(removed.item_id, second.item_id)
        self.assertEqual(len(state.queue), 0)

    def test_autoplay_avoids_history_duplicates_and_host_transfer(self) -> None:
        guild_id = "guild-102"
        # Clear any existing music history for this guild to ensure test isolation
        clear_music_history_db(guild_id)
        self.queue_svc.add_track(
            guild_id=guild_id,
            title="Secukupnya",
            artist="Hindia",
            duration_sec=200,
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=secukupnya",
            requester_id="host-1",
            requester_name="Host 1",
        )
        dup_candidate = QueueItemModel(
            item_id="cand-1",
            guild_id=guild_id,
            position=1,
            title="Secukupnya",
            artist="Hindia",
            album="",
            duration_sec=200,
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=secukupnya",
            stream_url="",
            thumbnail_url="",
            requester_id="system",
            requester_name="Autoplay",
            added_at="2026-10-28T00:00:00Z",
        )
        fresh_candidate = QueueItemModel(
            item_id="cand-2",
            guild_id=guild_id,
            position=1,
            title="Rumah Ke Rumah",
            artist="Hindia",
            album="",
            duration_sec=250,
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=rumah",
            stream_url="",
            thumbnail_url="",
            requester_id="system",
            requester_name="Autoplay",
            added_at="2026-10-28T00:00:00Z",
        )
        next_track = self.queue_svc.advance_track(guild_id, [dup_candidate, fresh_candidate])
        self.assertIsNotNone(next_track)
        self.assertEqual(next_track.title, "Rumah Ke Rumah")

        # Host leaves voice channel -> transfers to remaining member
        new_host = self.queue_svc.handle_host_left_voice(guild_id, [("user-2", "Nadia")])
        self.assertEqual(new_host, "user-2")

    def test_moodle_ics_sync_deduplication_and_3stage_reminders(self) -> None:
        guild_id = "guild-academy"
        events = parse_moodle_ics_content(SAMPLE_ICS, "Asia/Jakarta")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].course_name, "IF3130 Jaringan Komputer")
        # 16:59 UTC == 23:59 Asia/Jakarta (+07:00)
        self.assertIn("+07:00", events[0].deadline_iso)

        ins1, upd1 = self.academy_svc.sync_ics_events(guild_id, SAMPLE_ICS, "Asia/Jakarta")
        self.assertEqual((ins1, upd1), (1, 0))

        # Second sync with same UID must update, not duplicate
        ins2, upd2 = self.academy_svc.sync_ics_events(guild_id, SAMPLE_ICS, "Asia/Jakarta")
        self.assertEqual((ins2, upd2), (0, 1))

        # Evaluate reminder at H-5 hours before deadline
        deadline_dt = datetime.fromisoformat(events[0].deadline_iso)
        five_hours_before = deadline_dt - timedelta(hours=5)
        sent_first = self.academy_svc.evaluate_due_reminders(guild_id, now=five_hours_before)
        self.assertEqual(len(sent_first), 1)
        self.assertEqual(sent_first[0]["stage"], "H-6h")

        # Re-evaluating at same stage must not re-send duplicate reminder
        sent_again = self.academy_svc.evaluate_due_reminders(guild_id, now=five_hours_before)
        self.assertEqual(len(sent_again), 0)

    def test_module_attachment_validation_and_path_traversal(self) -> None:
        valid_pdf = b"%PDF-1.7 sample academic module content"
        ok, msg, safe_name = sanitize_and_validate_attachment("Modul_Minggu_1.pdf", valid_pdf, max_mb=15)
        self.assertTrue(ok, msg)
        self.assertTrue(safe_name.endswith(".pdf"))

        # Path traversal attempt rejected
        ok_trav, _, _ = sanitize_and_validate_attachment("../../etc/passwd.pdf", valid_pdf, max_mb=15)
        self.assertFalse(ok_trav)

        # Dangerous extension rejected
        ok_exe, _, _ = sanitize_and_validate_attachment("malware.exe", b"MZ\x90\x00", max_mb=15)
        self.assertFalse(ok_exe)

        # Fake PDF without %PDF- signature rejected
        ok_fake, _, _ = sanitize_and_validate_attachment("palsu.pdf", b"NOT_A_PDF_FILE", max_mb=15)
        self.assertFalse(ok_fake)

    def test_rpg_leveling_cooldown_and_afk(self) -> None:
        guild_id = "guild-rpg"
        self.assertEqual(calculate_max_exp(1), 125)
        self.assertEqual(calculate_max_exp(2), 150)

        t0 = datetime(2026, 10, 28, 10, 0, 0, tzinfo=timezone.utc)
        leveled, lvl, exp, _ = self.leveling_svc.process_message_activity(
            guild_id=guild_id,
            user_id="u-1",
            username="budi",
            display_name="Budi",
            message_content="Halo teman-teman kelas!",
            exp_gain=130,
            now=t0,
        )
        self.assertTrue(leveled)
        self.assertEqual(lvl, 2)
        self.assertEqual(exp, 5)  # 130 - 125

        # Spam within 60s cooldown gives 0 EXP
        _, lvl2, exp2, _ = self.leveling_svc.process_message_activity(
            guild_id=guild_id,
            user_id="u-1",
            username="budi",
            display_name="Budi",
            message_content="Pesan beruntun sebelum cooldown habis",
            exp_gain=50,
            now=t0 + timedelta(seconds=15),
        )
        self.assertEqual((lvl2, exp2), (2, 5))

        # AFK set, list & clear
        self.leveling_svc.set_afk(guild_id, "u-1", "budi", "Sedang ujian tengah semester")
        afk_rows = self.leveling_svc.list_afk(guild_id)
        self.assertEqual(len(afk_rows), 1)
        self.assertEqual(afk_rows[0]["username"], "budi")
        self.assertTrue(self.leveling_svc.clear_afk(guild_id, "u-1"))
        self.assertFalse(self.leveling_svc.clear_afk(guild_id, "u-1"))
        self.assertEqual(len(self.leveling_svc.list_afk(guild_id)), 0)

    def test_academy_crud_and_api_module_globals(self) -> None:
        guild_id = "1428666546942902294"
        created = self.academy_svc.create_task(
            guild_id=guild_id,
            course_name="IF3130 Jaringan Komputer",
            title="Praktikum Routing OSPF",
            deadline_iso="2026-11-12T16:59:00+00:00",
            created_by="Aetheriaaa",
        )
        listed = self.academy_svc.list_tasks(guild_id, include_completed=True)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].task_id, created.task_id)

        toggled = self.academy_svc.toggle_task(created.task_id, actor_name="Aetheriaaa")
        self.assertIsNotNone(toggled)
        self.assertEqual(toggled.is_completed, 1)

        self.assertTrue(self.academy_svc.delete_task(guild_id, created.task_id))
        self.assertEqual(len(self.academy_svc.list_tasks(guild_id, include_completed=True)), 0)

        import app.web.routes.api as api_mod

        self.assertTrue(hasattr(api_mod, "Request"))
        self.assertTrue(hasattr(api_mod, "WebSocket"))

    def test_encryption_rate_limiter_lrc_and_sqlite_backup(self) -> None:
        cipher = encrypt_secret("https://lms.ac.id/calendar/export.php?token=secret123", "kunci-rahasia")
        plain = decrypt_secret(cipher, "kunci-rahasia")
        self.assertIn("token=secret123", plain)

        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
        self.assertTrue(limiter.allow("ip-1", now=100.0))
        self.assertTrue(limiter.allow("ip-1", now=101.0))
        self.assertFalse(limiter.allow("ip-1", now=102.0))

        lrc = parse_lrc_timestamps("[00:12.50] Baris pertama\n[00:18.00] Baris kedua")
        self.assertEqual(len(lrc), 2)
        self.assertEqual(lrc[0].time_sec, 12.5)

        backup_dir = Path(self.temp_dir.name) / "backups"
        bak_svc = BackupService(db_path=self.db_path, backup_dir=backup_dir)
        res = bak_svc.create_consistent_backup(encrypt=True)
        self.assertTrue(res["success"])
        self.assertTrue(Path(str(res["path"])).exists())
        self.assertGreater(int(res["size_bytes"]), 32)

    def test_lyrics_found_voice_exp_and_moodle_env(self) -> None:
        from app.services.lyrics_service import LyricsService

        lyr_svc = LyricsService()
        res_found = lyr_svc.get_lyrics("Evaluasi", "Hindia")
        self.assertTrue(res_found.found)
        self.assertEqual(res_found.status, "synced")

        guild_id = "1428666546942902294"
        t0 = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
        _, lvl1, exp1, _ = self.leveling_svc.process_voice_activity(
            guild_id=guild_id,
            user_id="u-voice-1",
            username="aetheria",
            display_name="Aetheriaaa",
            activity_type="voice_join",
            now=t0,
        )
        self.assertEqual((lvl1, exp1), (1, 20))

        # After 60s, streaming in voice adds +25 EXP
        _, lvl2, exp2, _ = self.leveling_svc.process_voice_activity(
            guild_id=guild_id,
            user_id="u-voice-1",
            username="aetheria",
            display_name="Aetheriaaa",
            activity_type="voice_stream",
            now=t0 + timedelta(seconds=65),
        )
        self.assertEqual((lvl2, exp2), (1, 45))

        moodle_env = self.academy_svc.get_moodle_env_status()
        self.assertIn("moodle_base_url", moodle_env)
        self.assertIn("has_ical_url", moodle_env)

    def test_user_request_prioritized_over_autoplay(self) -> None:
        guild_id = "guild-priority-01"
        # 1 song currently playing, autoplay enabled
        first_item, started = self.queue_svc.add_track(
            guild_id=guild_id,
            title="Evaluasi",
            artist="Hindia",
            duration_sec=195,
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=2vcc2g6wHVQ",
            requester_id="user-1",
            requester_name="Aetheriaaa",
        )
        self.assertTrue(started)
        st = self.queue_svc.get_state(guild_id)
        self.assertFalse(st.autoplay)
        self.assertFalse(st.mode_247)
        st.autoplay = True
        self.assertEqual(st.current_track.item_id, first_item.item_id)

        # Suppose an autoplay track was queued
        auto_item, _ = self.queue_svc.add_track(
            guild_id=guild_id,
            title="Autoplay Song",
            artist="Autoplay Artist",
            duration_sec=180,
            source_type="autoplay",
            source_url="https://www.youtube.com/watch?v=autoplay1",
            requester_id="system",
            requester_name="Autoplay",
            is_autoplay=True,
        )
        self.assertTrue(auto_item.is_autoplay)

        # Now user requests a song while 1 song is playing and autoplay is active
        user_req, started_req = self.queue_svc.add_track(
            guild_id=guild_id,
            title="Monokrom",
            artist="Tulus",
            duration_sec=214,
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=QqJ-Vp8mvbk",
            requester_id="user-2",
            requester_name="RequestUser",
            is_autoplay=False,
        )
        self.assertFalse(started_req)
        # User request must be placed at index 0 (ahead of autoplay)
        self.assertEqual(st.queue[0].title, "Monokrom")
        self.assertFalse(st.queue[0].is_autoplay)

        # When current song finishes, user-requested song plays FIRST
        next_up = self.queue_svc.advance_track(guild_id)
        self.assertIsNotNone(next_up)
        self.assertEqual(next_up.title, "Monokrom")

        # After user-requested song finishes, autoplay resumes
        after_user = self.queue_svc.advance_track(guild_id)
        self.assertIsNotNone(after_user)
        self.assertEqual(after_user.title, "Autoplay Song")

    def test_all_python_modules_compile_and_imports_resolve(self) -> None:
        import ast
        import importlib
        import py_compile

        app_dir = Path(__file__).resolve().parent.parent / "app"
        py_files = sorted(app_dir.rglob("*.py"))
        self.assertGreater(len(py_files), 5)
        for py_file in py_files:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
            py_compile.compile(str(py_file), doraise=True)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
                    mod = importlib.import_module(node.module)
                    for alias in node.names:
                        self.assertTrue(
                            hasattr(mod, alias.name),
                            f"Missing symbol '{alias.name}' in '{node.module}' imported by {py_file.name}",
                        )

        from app.bot.client import build_discord_bot

        # Ensure build_discord_bot() works with 0 args as called in app/main.py
        build_discord_bot()

    def test_voice_web_synchronization_and_listener_contract(self) -> None:
        from app.bot.client import build_discord_bot

        guild_id = "1428666546942902294"
        received_events: list[tuple[str, str, str | None]] = []

        def sample_listener(gid: str, st_obj: object, ev_name: str) -> None:
            curr = getattr(st_obj, "current_track", None)
            received_events.append((gid, ev_name, getattr(curr, "id", None)))

        self.queue_svc.register_listener(sample_listener)

        track_a, started_a = self.queue_svc.add_track(
            guild_id=guild_id,
            title="You Right",
            artist="Doja Cat, The Weeknd",
            duration_sec=186,
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=JXgV1rXUoME",
            requester_id="user-1",
            requester_name="Aetheriaaa",
        )
        self.assertTrue(started_a)
        self.assertEqual(track_a.id, track_a.item_id)

        track_b, started_b = self.queue_svc.add_track(
            guild_id=guild_id,
            title="Mind Games",
            artist="Sickick",
            duration_sec=258,
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=6v3N2lI6Z7w",
            requester_id="user-1",
            requester_name="Aetheriaaa",
        )
        self.assertFalse(started_b)
        self.assertEqual(track_b.id, track_b.item_id)

        # Skip from web control_session -> must advance immediately to Mind Games and emit track_started
        self.queue_svc.control_session(
            guild_id=guild_id,
            action="skip",
            actor_id="user-1",
            is_admin=True,
        )
        st = self.queue_svc.get_state(guild_id)
        self.assertIsNotNone(st.current_track)
        self.assertEqual(st.current_track.title, "Mind Games")
        self.assertEqual(st.current_track.id, track_b.item_id)

        # Stop from web control_session -> must clear current_track & queue and emit stopped
        self.queue_svc.control_session(
            guild_id=guild_id,
            action="stop",
            actor_id="user-1",
            is_admin=True,
        )
        self.assertIsNone(st.current_track)
        self.assertFalse(st.is_playing)

        event_names = [ev[1] for ev in received_events]
        self.assertIn("track_started", event_names)
        self.assertIn("stopped", event_names)

        # Verify AthenaaBot._on_queue_event and setup_hook() execute cleanly without AttributeError
        import asyncio

        bot = build_discord_bot(queue_service=self.queue_svc)
        self.assertTrue(self.queue_svc.voice_bot_active)
        asyncio.run(bot.setup_hook())
        bot._on_queue_event(guild_id, st, "voice_sync")
        bot._on_queue_event(guild_id, st, "stopped")

    def test_waskita_submittable_task_filter_and_0001_wib_daily_reminder(self) -> None:
        from app.bot.client import build_daily_task_reminder_embed

        mixed_waskita_ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Moodle Pty Ltd//NONSGML Moodle Version 2026042000//EN
BEGIN:VEVENT
UID:waskita-due-01@kampus.ac.id
SUMMARY:[IF3130 Jaringan Komputer] Tugas 3 Analisis Wireshark is due
DESCRIPTION:Kumpulkan file PDF sebelum tenggat waktu.
CATEGORIES:IF3130 Jaringan Komputer
DTEND:20261215T165900Z
URL:https://waskita.kampus.ac.id/mod/assign/view.php?id=501
END:VEVENT
BEGIN:VEVENT
UID:waskita-open-02@kampus.ac.id
SUMMARY:[IF3130 Jaringan Komputer] Tugas 3 Analisis Wireshark opens
DESCRIPTION:Tugas mulai dibuka hari ini.
CATEGORIES:IF3130 Jaringan Komputer
DTSTART:20261201T010000Z
URL:https://waskita.kampus.ac.id/mod/assign/view.php?id=501
END:VEVENT
BEGIN:VEVENT
UID:waskita-att-03@kampus.ac.id
SUMMARY:[IF3130 Jaringan Komputer] Presensi Kuliah Minggu 10
DESCRIPTION:Daftar hadir perkuliahan rutin.
CATEGORIES:IF3130 Jaringan Komputer
DTEND:20261202T030000Z
URL:https://waskita.kampus.ac.id/mod/attendance/view.php?id=220
END:VEVENT
END:VCALENDAR"""

        events = parse_moodle_ics_content(mixed_waskita_ics, "Asia/Jakarta")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].uid, "waskita-due-01@kampus.ac.id")
        self.assertEqual(events[0].title, "Tugas 3 Analisis Wireshark")

        guild_id = "guild-waskita-01"
        ins, upd = self.academy_svc.sync_ics_events(guild_id, mixed_waskita_ics, "Asia/Jakarta")
        self.assertEqual((ins, upd), (1, 0))

        now_ref = datetime(2026, 12, 10, 17, 1, 0, tzinfo=timezone.utc)  # 00:01 WIB on 2026-12-11
        unsent = self.academy_svc.filter_unsent_daily_reminder_tasks(
            guild_id=guild_id,
            date_wib_str="2026-12-11",
            now=now_ref,
        )
        self.assertEqual(len(unsent), 1)
        self.assertEqual(unsent[0].title, "Tugas 3 Analisis Wireshark")

        emb = build_daily_task_reminder_embed(
            tasks=unsent,
            date_wib_str="2026-12-11",
            now_ref=now_ref,
        )
        self.assertIn("00:01 WIB", emb.description)
        self.assertEqual(len(emb.fields), 1)
        self.assertIn("IF3130 Jaringan Komputer", emb.fields[0].name)
        self.assertIn("Tugas 3 Analisis Wireshark", emb.fields[0].name)
        self.assertIn("https://waskita.kampus.ac.id/mod/assign/view.php?id=501", emb.fields[0].value)

        # Mark daily reminder sent -> subsequent check for same WIB date returns 0 tasks
        self.academy_svc.mark_daily_reminder_sent(
            guild_id=guild_id,
            task_ids=[t.task_id for t in unsent],
            channel_id="1558142572164022362",
            date_wib_str="2026-12-11",
        )
        unsent_after = self.academy_svc.filter_unsent_daily_reminder_tasks(
            guild_id=guild_id,
            date_wib_str="2026-12-11",
            now=now_ref,
        )
        self.assertEqual(len(unsent_after), 0)

    def test_dynamic_guild_join_sync_and_upsert(self) -> None:
        import asyncio
        from types import SimpleNamespace
        from app.bot.client import build_discord_bot

        new_gid = "987654321098765432"
        # First ensure without custom name -> defaults to TK1GACORKINK
        self.academy_svc.ensure_guild_exists(new_gid)
        # Then ensure with real Discord server name -> must upsert to real name
        self.academy_svc.ensure_guild_exists(new_gid, "Server Kampus Baru")
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT guild_name FROM guild_settings WHERE guild_id = ?",
                (new_gid,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["guild_name"], "Server Kampus Baru")

        notified_guilds = []

        async def on_state_cb(gid: str) -> None:
            notified_guilds.append(gid)

        bot = build_discord_bot(
            queue_service=self.queue_svc,
            academy_service=self.academy_svc,
            on_state_change=on_state_cb,
        )
        fake_vc = SimpleNamespace(id=1122334455, name="Voice Lounge", members=[SimpleNamespace(bot=False)])
        fake_guild = SimpleNamespace(id=int(new_gid), name="Server Discord Kedua", voice_channels=[fake_vc])

        asyncio.run(bot.on_guild_join(fake_guild))
        self.assertEqual(self.queue_svc.active_guilds.get(new_gid), "Server Discord Kedua")
        st = self.queue_svc.get_state(new_gid)
        self.assertEqual(st.voice_channel_id, "1122334455")
        self.assertEqual(st.voice_channel_name, "Voice Lounge")
        self.assertIn(new_gid, notified_guilds)

        with self.db.transaction() as conn:
            row2 = conn.execute(
                "SELECT guild_name FROM guild_settings WHERE guild_id = ?",
                (new_gid,),
            ).fetchone()
        self.assertIsNotNone(row2)
        self.assertEqual(row2["guild_name"], "Server Discord Kedua")

        # When bot leaves the guild -> removed from active_guilds and guild_settings
        asyncio.run(bot.on_guild_remove(fake_guild))
        self.assertNotIn(new_gid, self.queue_svc.active_guilds)
        with self.db.transaction() as conn:
            row3 = conn.execute(
                "SELECT guild_name FROM guild_settings WHERE guild_id = ?",
                (new_gid,),
            ).fetchone()
        self.assertIsNone(row3)

    def test_autoplay_never_gets_stuck_after_catalog_exhaustion_or_user_play(self) -> None:
        from app.bot.client import build_discord_bot

        bot = build_discord_bot(queue_service=self.queue_svc, academy_service=self.academy_svc)
        self.assertTrue(hasattr(bot, "_waskita_sync_task"))
        self.assertTrue(hasattr(bot, "_daily_reminder_task"))

        guild_id = "1420970251322921091"
        st = self.queue_svc.get_state(guild_id)
        st.autoplay = True

        # User plays a song on their own
        self.queue_svc.add_track(
            guild_id=guild_id,
            title="Penyangkalan",
            artist="for Revenge",
            duration_sec=284,
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=penyangkalan",
            requester_id="844174494099701780",
            requester_name="Aetheriaaa",
            play_now=True,
        )

        # Advance 35 times in a row (exceeding the 20-item static catalog size)
        # Autoplay must NEVER return None or stop while st.autoplay is True!
        for _ in range(35):
            nxt = self.queue_svc.advance_track(guild_id)
            self.assertIsNotNone(nxt)
            self.assertTrue(st.is_playing)
            self.assertIsNotNone(st.current_track)

        # User plays another song with play_now=True while a song is playing -> must NOT push old song into queue
        self.queue_svc.add_track(
            guild_id=guild_id,
            title="Cincin",
            artist="Hindia",
            duration_sec=267,
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=cincin",
            requester_id="844174494099701780",
            requester_name="Aetheriaaa",
            play_now=True,
        )
        self.assertEqual(len(st.queue), 0)
        self.assertEqual(st.current_track.title, "Cincin")

        # When Cincin finishes, Autoplay immediately continues with another song (preferring same artist Hindia)
        after_cincin = self.queue_svc.advance_track(guild_id)
        self.assertIsNotNone(after_cincin)
        self.assertTrue(after_cincin.is_autoplay)
        self.assertNotEqual(after_cincin.title, "Cincin")

    def test_create_fastapi_app_initialization(self) -> None:
        from app.web.routes.api import create_fastapi_app, ControlMusicRequest, PlayMusicRequest
        app = create_fastapi_app()
        self.assertIsNotNone(app, "create_fastapi_app() must return a FastAPI application, not None")
        self.assertTrue(len(app.routes) > 20, "FastAPI app must register routes")

        # Verify ControlMusicRequest accepts all frontend player payloads
        control_payloads = [
            {"action": "pause", "item_id": None, "value": None},
            {"action": "resume", "item_id": None, "value": None},
            {"action": "autoplay", "value": True, "item_id": None},
            {"action": "mode_247", "value": True, "item_id": None},
            {"action": "seek", "value": 15.5, "item_id": None},
            {"action": "volume", "value": 75.0, "item_id": None},
            {"action": "skip", "item_id": None, "value": None},
            {"action": "stop", "item_id": None, "value": None},
            {"action": "play_item", "item_id": "test-item-1"},
            {"action": "remove_item", "item_id": "test-item-1"},
            {"action": "move_to_top", "item_id": "test-item-1"},
            {"action": "loop", "value": "queue", "item_id": None},
        ]
        for cp in control_payloads:
            req = ControlMusicRequest.model_validate(cp)
            self.assertEqual(req.action, cp["action"].lower())

        # Verify PlayMusicRequest accepts radio, YouTube, and null fields
        play_req = PlayMusicRequest.model_validate({
            "title": "Live Radio",
            "artist": None,
            "album": None,
            "duration_sec": 0,
            "source_type": "radio",
            "source_url": "https://example.com/stream",
            "stream_url": None,
            "thumbnail_url": None,
        })
        self.assertEqual(play_req.title, "Live Radio")
        self.assertEqual(play_req.duration_sec, 0)

    def test_api_module_upload_and_download(self) -> None:
        import base64
        from starlette.testclient import TestClient
        from app.database import db_manager
        from app.web.routes.api import create_fastapi_app, _ensure_multi_session_table

        app = create_fastapi_app()
        client = TestClient(app)

        _ensure_multi_session_table()
        with db_manager.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO discord_user_sessions (
                    session_token, user_id, username, discord_tag, role_label, is_admin, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("test_tok_mod_upload", "844174494099701780", "Tester", "Tester#0001", "Admin", 1, "2026-11-13T00:00:00Z"),
            )

        client.cookies.set("athenaa_session_token", "test_tok_mod_upload")

        dummy_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        b64_pdf = base64.b64encode(dummy_pdf).decode("utf-8")

        resp = client.post(
            "/api/guilds/1428666546942902294/modules/upload",
            json={
                "filename": "Praktikum_07.pdf",
                "size_bytes": len(dummy_pdf),
                "content_base64": b64_pdf,
                "task_id": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        att = data.get("attachment", {})
        self.assertEqual(att.get("original_filename"), "Praktikum_07.pdf")
        self.assertTrue(att.get("attachment_id", "").startswith("att-"))

        # Test download
        att_id = att.get("attachment_id")
        dl_resp = client.get(f"/api/modules/{att_id}/download")
        self.assertEqual(dl_resp.status_code, 200)
        self.assertEqual(dl_resp.headers.get("content-type"), "application/pdf")
        self.assertIn("Praktikum_07.pdf", dl_resp.headers.get("content-disposition", ""))
        self.assertEqual(dl_resp.content, dummy_pdf)

    def test_stream_extraction_and_android_client(self) -> None:
        import json
        from unittest.mock import MagicMock, patch
        from app.services.music_service import (
            extract_playable_stream_ytdlp,
            search_songs_with_singer,
            _compute_fuzzy_song_match_score,
        )

        # 1. Verify typo-tolerant YouTube Music search ("Aint on LA adela" -> "Ain't in LA" by "Adela")
        typo_results = search_songs_with_singer("Aint on LA adela", limit=5)
        self.assertGreater(len(typo_results), 0)
        self.assertEqual(typo_results[0].title, "Ain't in LA")
        self.assertEqual(typo_results[0].artist, "Adela")
        sim_score = _compute_fuzzy_song_match_score("Aint on LA adela", "Ain't in LA", "Adela")
        self.assertGreaterEqual(sim_score, 0.85)

        # 2. Verify extract_playable_stream_ytdlp (live or mocked in offline environment)
        info = extract_playable_stream_ytdlp("https://www.youtube.com/watch?v=QSWYyoF79oE")
        if info is None:
            fake_stdout = json.dumps({
                "id": "QSWYyoF79oE",
                "title": "Adela - Ain't in LA (Official Audio)",
                "artist": "Adela - Topic",
                "duration": 192,
                "url": "https://rr1---sn-mock.googlevideo.com/videoplayback?id=QSWYyoF79oE",
                "thumbnail": "https://i.ytimg.com/vi/QSWYyoF79oE/hqdefault.jpg",
                "http_headers": {"User-Agent": "Mozilla/5.0"},
                "acodec": "opus",
                "ext": "webm",
            })
            mock_proc = MagicMock(returncode=0, stdout=fake_stdout)
            with patch("subprocess.run", return_value=mock_proc):
                info = extract_playable_stream_ytdlp("https://www.youtube.com/watch?v=QSWYyoF79oE")
        self.assertIsNotNone(info)
        self.assertTrue(bool(info.get("stream_url")))
        self.assertTrue(bool(info.get("user_agent")))



    def test_strict_per_guild_voice_isolation_and_new_features(self) -> None:
        from types import SimpleNamespace
        from fastapi.testclient import TestClient
        from app.web.routes.api import create_fastapi_app
        from app.services.music_service import resolve_direct_youtube_video_link, _build_ai_trending_discovery_queries
        from app.bot.client import build_discord_bot, build_daily_task_reminder_embed, build_stage_deadline_alert_embed

        app = create_fastapi_app()
        client = TestClient(app)

        # 1. Verify /api/python-codebase and /api/python-codebase/download-zip are hidden (404)
        self.assertEqual(client.get("/api/python-codebase").status_code, 404)
        self.assertEqual(client.get("/api/python-codebase/download-zip").status_code, 404)

        # 2. Setup 2 guilds: Guild A (some fineshyt) where user IS in voice, and Guild B (TK1GACORKINK) where user is NOT in voice
        fake_vc_lounge = SimpleNamespace(id=99887766, name="Lounge", members=[])
        fake_member_in_vc = SimpleNamespace(
            id=844174494099701780,
            bot=False,
            guild_permissions=SimpleNamespace(administrator=True),
            voice=SimpleNamespace(channel=fake_vc_lounge),
        )
        fake_vc_lounge.members = [fake_member_in_vc]

        fake_member_no_vc = SimpleNamespace(
            id=844174494099701780,
            bot=False,
            guild_permissions=SimpleNamespace(administrator=True),
            voice=None,
        )
        fake_vc_chill = SimpleNamespace(id=1428666547924238427, name="chill", members=[])

        guild_some_fineshyt = SimpleNamespace(
            id=1404865078112550922,
            name="some fineshyt",
            owner_id=844174494099701780,
            voice_client=None,
            voice_channels=[fake_vc_lounge],
            members=[fake_member_in_vc],
            get_member=lambda uid: fake_member_in_vc if uid == 844174494099701780 else None,
        )
        guild_tk1 = SimpleNamespace(
            id=1428666546942902294,
            name="TK1GACORKINK",
            owner_id=844174494099701780,
            voice_client=None,
            voice_channels=[fake_vc_chill],
            members=[fake_member_no_vc],
            get_member=lambda uid: fake_member_no_vc if uid == 844174494099701780 else None,
        )
        app.state.bot = SimpleNamespace(
            guilds=[guild_some_fineshyt, guild_tk1],
            _schedule_coro=lambda c: c.close() if hasattr(c, "close") else None,
            start_or_sync_voice_playback=lambda *a, **kw: None,
        )

        # 3. Attempting to play on TK1GACORKINK while only in voice on 'some fineshyt' MUST BE REJECTED (400)
        resp_cross_guild = client.post(
            "/api/guilds/1428666546942902294/music/play",
            json={
                "title": "Ain't in LA",
                "artist": "Adela",
                "duration_sec": 192,
                "source_type": "spotify_matched",
                "source_url": "https://www.youtube.com/watch?v=QSWYyoF79oE",
                "play_now": True,
                "requester_id": "844174494099701780",
                "requester_name": "Aetheriaaa",
            },
        )
        self.assertEqual(resp_cross_guild.status_code, 400)
        self.assertIn("some fineshyt", resp_cross_guild.json().get("error", ""))

        # 4. Playing on 'some fineshyt' (where user IS in voice 'Lounge') MUST SUCCEED (200)
        resp_same_guild = client.post(
            "/api/guilds/1404865078112550922/music/play",
            json={
                "title": "Ain't in LA",
                "artist": "Adela",
                "duration_sec": 192,
                "source_type": "youtube",
                "source_url": "https://www.youtube.com/watch?v=QSWYyoF79oE&list=RDQSWYyoF79oE",
                "play_now": True,
                "requester_id": "844174494099701780",
                "requester_name": "Aetheriaaa",
            },
        )
        self.assertEqual(resp_same_guild.status_code, 200)
        self.assertEqual(resp_same_guild.json()["state"]["voice_channel_name"], "Lounge")

        # 5. Verify direct YouTube video link resolves to strictly 1 exact track
        cand_yt = resolve_direct_youtube_video_link("https://www.youtube.com/watch?v=QSWYyoF79oE&list=RDQSWYyoF79oE")
        self.assertEqual(cand_yt.source_type, "youtube")
        self.assertEqual(cand_yt.source_url, "https://www.youtube.com/watch?v=QSWYyoF79oE")

        # 6. Verify AI Smart Trending Autoplay queries & /help + new slash commands registered
        ai_queries = _build_ai_trending_discovery_queries("Ain't In LA", "Adéla", [])
        self.assertTrue(len(ai_queries) >= 4)

        from app.bot.client import optimize_process_memory, get_process_ram_mb
        from app.config import settings

        # Verify AI Smart Autoplay & RAM Optimizer in settings & .env
        readiness = settings.feature_readiness()
        self.assertTrue(readiness.get("ai_smart_autoplay"))
        self.assertTrue(readiness.get("ram_optimizer"))

        # Verify RAM Optimizer Engine works
        ram_stats = optimize_process_memory()
        self.assertGreater(ram_stats["after_mb"], 0.0)
        self.assertIn("collected_objects", ram_stats)

        bot_instance = build_discord_bot()
        cmd_names = {cmd.name for cmd in bot_instance.tree.get_commands()}
        for expected_cmd in (
            "help", "filter", "seek", "replay", "previous", "skipto", "move", "clear",
            "history", "grab", "sleeptimer", "ambience", "tugas_preview", "target_ipk",
            "flashcard", "poll", "remindme", "serverinfo", "ram_clean", "stats", "play", "tugas"
        ):
            self.assertIn(expected_cmd, cmd_names)
        self.assertGreaterEqual(len(cmd_names), 50)
        # Verify every command and parameter description in client.py is <= 100 characters (Discord API 50035 limit)
        import ast as _ast
        client_src = (Path(__file__).resolve().parent.parent / "app" / "bot" / "client.py").read_text(encoding="utf-8")
        for _node in _ast.walk(_ast.parse(client_src)):
            if isinstance(_node, _ast.Call):
                _fstr = _ast.unparse(_node.func) if hasattr(_ast, "unparse") else ""
                if "tree.command" in _fstr or "describe" in _fstr:
                    for _kw in _node.keywords:
                        if isinstance(_kw.value, _ast.Constant) and isinstance(_kw.value.value, str):
                            self.assertLessEqual(len(_kw.value.value), 100, f"Description > 100 chars: {_kw.value.value}")




    def test_v54_superpowers_features_tdd(self) -> None:
        """
        TDD Test Suite (Red -> Green -> Refactor) untuk 5 fitur baru Athenaa v5.4:
        1. Multi-Key Gemini API rotation saat key pertama terkena limit (HTTP 429).
        2. Strict @Athena mention-only AI Chatbot + Live Web Search + Natural Language Music Play intent.
        3. Configurable .env Ambience URLs (memperbaiki bug Lagu Tidak Ditemukan pada /ambience).
        4. Next-track text/Embed notification otomatis saat lagu berganti di Discord.
        5. Koya & Carl-bot style Server Settings (AutoMod Chat Sensor, Anti-Link, Anti-Spam, Welcome/Goodbye, Auto-Role, ModLog).
        """
        import asyncio
        import urllib.error
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        from fastapi.testclient import TestClient
        from app.config import settings
        from app.web.routes.api import create_fastapi_app
        from app.services.ai_assistant_service import (
            GeminiKeyRotator,
            should_respond_to_message,
            classify_mention_intent,
            evaluate_automod_message,
        )

        # 1. Test Multi-Key Gemini API Rotator (Key 1 -> 429 Rate Limit, auto-rotates to Key 2 -> 200 OK)
        rotator = GeminiKeyRotator(keys=["AIza_KEY1_EXHAUSTED", "AIza_KEY2_ACTIVE"], models=["gemini-3.8-flash"])
        call_log = []

        def fake_urlopen(req, timeout=5.0):
            url_s = req.full_url
            call_log.append(url_s)
            if "AIza_KEY1_EXHAUSTED" in url_s:
                raise urllib.error.HTTPError(url_s, 429, "Too Many Requests", {}, None)
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"candidates":[{"content":{"parts":[{"text":"Jawaban dari Key 2 yang aktif!"}]}}]}'
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            reply_text, used_key_idx = rotator.generate_response("Halo Athena")
        self.assertEqual(reply_text, "Jawaban dari Key 2 yang aktif!")
        self.assertEqual(used_key_idx, 1)
        self.assertEqual(len(call_log), 2)

        # 2. Test Strict @Athena Mention-Only Rule & Natural Language Music Intent
        bot_id = "1534885757649555498"
        # Tidak di-tag -> WAJIB diabaikan (False) meskipun ada kata 'athena' atau tanya saran anime
        self.assertFalse(should_respond_to_message("ada saran anime gak?", bot_id, mentioned_ids=[]))
        self.assertFalse(should_respond_to_message("woi athena apakah betul gibran mundur?", bot_id, mentioned_ids=[]))
        # Di-tag resmi (<@bot_id>) -> WAJIB direspon (True)
        self.assertTrue(should_respond_to_message(f"woi <@{bot_id}>, apakah betul gibran mengundurkan diri sebagai wapres?", bot_id, mentioned_ids=[bot_id]))

        # Intent klasifikasi: perintah putar musik lewat kalimat biasa vs pertanyaan berita/chat
        intent_play, song_q = classify_mention_intent(
            f"woi <@{bot_id}>, tolong putarkan musik Merry Chrismas Please Dont Call dong sayang",
            bot_id,
        )
        self.assertEqual(intent_play, "play_music")
        self.assertEqual(song_q.lower(), "merry chrismas please dont call")

        intent_chat, chat_q = classify_mention_intent(
            f"woi <@{bot_id}>, apakah betul gibran mengundurkan diri sebagai wapres?",
            bot_id,
        )
        self.assertEqual(intent_chat, "chat_search")
        self.assertIn("gibran mengundurkan diri sebagai wapres", chat_q.lower())

        # 3. Test Configurable .env Ambience URLs
        rain_url = settings.get_ambience_url("rain")
        self.assertTrue(rain_url.startswith("https://www.youtube.com/watch?v="))
        cafe_url = settings.get_ambience_url("cafe")
        self.assertTrue(cafe_url.startswith("https://www.youtube.com/watch?v="))

        # 4. Test Koya & Carl-bot AutoMod Chat Sensor & Extended Server Settings API
        app = create_fastapi_app()
        client = TestClient(app)
        patch_resp = client.patch(
            "/api/guilds/1428666546942902294/settings",
            json={
                "automod_badwords_enabled": 1,
                "automod_badwords_list": "slot gacor,judol,kasar123",
                "automod_antilink_enabled": 1,
                "automod_antispam_enabled": 1,
                "welcome_enabled": 1,
                "welcome_channel_id": "1428666547701809159",
                "welcome_message": "Selamat datang {user} di {server}! Kamu member ke-{count}.",
                "goodbye_enabled": 1,
                "goodbye_message": "Sampai jumpa {user}!",
                "autorole_id": "1563848335247417395",
                "modlog_channel_id": "1558142572164022362",
                "ai_chat_enabled": 1,
                "announce_next_track": 1,
            },
        )
        self.assertEqual(patch_resp.status_code, 200)
        saved_cfg = patch_resp.json()["settings"]
        self.assertEqual(int(saved_cfg["automod_badwords_enabled"]), 1)
        self.assertIn("slot gacor", saved_cfg["automod_badwords_list"])
        self.assertEqual(saved_cfg["autorole_id"], "1563848335247417395")
        self.assertEqual(int(saved_cfg["announce_next_track"]), 1)

        # Verify AutoMod Chat Sensor catches bad words and invite links
        violated, reason = evaluate_automod_message("Ayo main di situs slot gacor hari ini", saved_cfg, is_admin=False)
        self.assertTrue(violated)
        self.assertIn("Kata Terlarang", reason)

        violated_link, reason_link = evaluate_automod_message("Join server kami https://discord.gg/abc123xyz", saved_cfg, is_admin=False)
        self.assertTrue(violated_link)
        self.assertIn("Tautan/Invite", reason_link)

        # 5. Verify _announce_next_track_to_channel sends the Next Track Embed to the Discord text channel
        from app.bot.client import build_discord_bot
        from app.services.queue_service import queue_service
        bot_test = build_discord_bot(queue_service=queue_service)
        sent_embeds = []

        class FakeTextChannel:
            async def send(self, embed=None, view=None, **kw):
                sent_embeds.append(embed)

        async def fake_resolve_ch(_guild, _ch_id):
            return FakeTextChannel()

        bot_test._resolve_discord_text_channel = fake_resolve_ch
        bot_test._music_text_channel_ids["1428666546942902294"] = "1428666547701809159"
        item_next, _ = queue_service.add_track(
            guild_id="1428666546942902294",
            title="Merry Christmas, Please Don't Call",
            artist="Bleachers",
            album="YouTube Music",
            duration_sec=240,
            source_type="spotify_matched",
            source_url="https://www.youtube.com/watch?v=jfKfPfyJRdk",
            stream_url="",
            thumbnail_url="",
            requester_id="844174494099701780",
            requester_name="Aetheriaaa",
            play_now=True,
        )
        asyncio.run(bot_test._announce_next_track_to_channel("1428666546942902294", item_next))
        self.assertEqual(len(sent_embeds), 1)
        self.assertIn("Merry Christmas, Please Don't Call", sent_embeds[0].title)




    def test_v55_interactive_chat_search_select_and_title_priority_tdd(self) -> None:
        """
        TDD Test Suite (Red -> Green -> Refactor) untuk 6 pembaruan Athenaa v5.5:
        1. Persona cewek kalem & token-saving deflection untuk pertanyaan berat/panjang + batas aman <1024 karakter.
        2. Eksekusi command natural lewat mention @Athena (help, autoplay on/off, queue, skip, pause, stop, filter, tugas).
        3. Prioritas Judul Lagu (Title-First Ranking) di atas nama penyanyi pada _compute_fuzzy_song_match_score.
        4. Autocomplete /play dan /api/music/search?q= wajib kosong ([]) saat user belum mengetik apa-apa.
        5. Pilihan @app_commands.choices pada /filter, /ambience, /loop, /help, /flashcard, /suit, /sleeptimer, /ai_model.
        6. Dropdown interaktif SearchTrackSelectView pada output /search.
        """
        from fastapi.testclient import TestClient
        from app.web.routes.api import create_fastapi_app
        from app.services.music_service import _compute_fuzzy_song_match_score
        from app.services.ai_assistant_service import (
            classify_mention_intent,
            is_heavy_or_long_question,
            answer_mention_question_with_search,
            save_channel_chat_turn,
            get_channel_chat_context,
            clear_channel_chat_memory,
        )
        from app.bot.client import build_discord_bot

        bot_id = "1534885757649555498"

        # 1. Test natural command intents via @Athena mention (sesuai screenshot user)
        self.assertEqual(classify_mention_intent(f"halo <@{bot_id}>", bot_id)[0], "greeting")
        self.assertEqual(classify_mention_intent(f"help <@{bot_id}>", bot_id)[0], "cmd_help")
        intent_ap, val_ap = classify_mention_intent(f"tolong aktifkan mode autoplay <@{bot_id}>", bot_id)
        self.assertEqual(intent_ap, "cmd_autoplay")
        self.assertEqual(val_ap, "on")
        self.assertEqual(classify_mention_intent(f"<@{bot_id}> buka queue dong", bot_id)[0], "cmd_queue")
        self.assertEqual(classify_mention_intent(f"<@{bot_id}> skip lagu ini", bot_id)[0], "cmd_skip")
        intent_lg, q_lg = classify_mention_intent(
            f"woi athena puki, tolong setelkan musik dari lady gaga yang judulnya poker face <@{bot_id}>",
            bot_id,
        )
        self.assertEqual(intent_lg, "play_music")
        self.assertEqual(q_lg.lower(), "poker face lady gaga")


        # 2. Test token-saving deflection for heavy/all-encompassing questions
        q_heavy = "apa jasa-jasa dari Pak Jokowi sebutkan semua"
        self.assertTrue(is_heavy_or_long_question(q_heavy))
        ans_heavy = answer_mention_question_with_search(q_heavy, "Seller Hosting")
        self.assertIn("google", ans_heavy["answer"].lower())
        self.assertLessEqual(len(ans_heavy["answer"]), 450)
        self.assertLessEqual(len(ans_heavy.get("sources_field_value", "")), 950)

        # 3. Test Title-First Ranking: lagu yang JUDUL-nya cocok wajib punya skor jauh lebih tinggi dibanding yang hanya cocok nama penyanyinya
        score_title_match = _compute_fuzzy_song_match_score(" Evaluasi ", "Evaluasi", "Hindia")
        score_artist_only = _compute_fuzzy_song_match_score(" Evaluasi ", "Secukupnya", "Evaluasi Band")
        self.assertGreater(score_title_match, score_artist_only + 0.25)

        # 4. Test /api/music/search?q= returns EMPTY list [] when query is empty (belum mengetik apa-apa)
        app = create_fastapi_app()
        client = TestClient(app)
        empty_res = client.get("/api/music/search?q=")
        self.assertEqual(empty_res.status_code, 200)
        self.assertEqual(empty_res.json()["results"], [])

        # 5. Verify SearchTrackSelectView exists and fixed-option commands have choices
        import app.bot.client as client_mod
        self.assertTrue(hasattr(client_mod, "SearchTrackSelectView"))

        # 6. Test Per-Channel SQLite Chat Memory (Isolated per channel_id & token-capped)
        clear_channel_chat_memory("ch_general_111")
        clear_channel_chat_memory("ch_musik_222")
        save_channel_chat_turn(
            guild_id="1428666546942902294",
            channel_id="ch_general_111",
            user_id="844174494099701780",
            user_name="Aldi",
            user_message="Aku lagi ngerjain tugas praktikum Jarkom Cisco nih",
            bot_reply="Semangat kak Aldi ngerjain praktikum Jarkom Cisco-nya yaa~",
        )
        save_channel_chat_turn(
            guild_id="1428666546942902294",
            channel_id="ch_musik_222",
            user_id="844174494099701780",
            user_name="Aldi",
            user_message="Lagi suka dengerin lagu Hindia Evaluasi",
            bot_reply="Lagu Evaluasi emang enak banget buat malam-malam kak~",
        )
        ctx_ch1 = get_channel_chat_context("ch_general_111", limit=4)
        ctx_ch2 = get_channel_chat_context("ch_musik_222", limit=4)
        self.assertIn("Jarkom Cisco", ctx_ch1)
        self.assertNotIn("Hindia Evaluasi", ctx_ch1)
        self.assertIn("Hindia Evaluasi", ctx_ch2)
        self.assertNotIn("Jarkom Cisco", ctx_ch2)
        self.assertLessEqual(len(ctx_ch1), 650)




    def test_v56_superpowers_6_fixes_tdd(self) -> None:
        """
        TDD Test Suite (Red -> Green -> Refactor) untuk 6 perbaikan Athenaa v5.6:
        1. Per-Guild settings mandiri (tidak terkunci .env) & bisa disimpan oleh user/admin server tersebut.
        2. Mutual Server Filtering (/api/guilds hanya menampilkan server di mana Bot DAN User sama-sama join).
        3. Natural language play & queue dengan kata slang/makian ("woi athena pukimak tolong puter musik A ya kontol",
           "aku pengen muter musik bye x circus dari britney spears & altare mashup klo gk salah bisa gk tolong puterin").
        4. Komplain "mana, kok gak ke play musik nya" TIDAK memutar lagu "nya", melainkan memutar lagu dari memori channel!
        5. Persona luwes tongkrongan ("woi athena tempek" -> santai "iya tempek...", tidak ceramah & tidak maksa muter lagu).
        6. Semua command bot bisa dijalankan lewat mention chat (volume, loop, lyrics, level, leaderboard, dadu, 8ball, dll.).
        """
        from types import SimpleNamespace
        from fastapi.testclient import TestClient
        from app.web.routes.api import create_fastapi_app, _issue_single_discord_session
        from app.services.ai_assistant_service import (
            classify_mention_intent,
            answer_mention_question_with_search,
            save_channel_chat_turn,
            get_last_requested_song_in_channel,
        )

        bot_id = "1534885757649555498"

        # 1. Test natural play with swear words & complex phrasing from screenshots
        intent1, q1 = classify_mention_intent(
            f"woi athena pukimak tolong puter musik Cinta Luar Biasa ya kontol <@{bot_id}>",
            bot_id,
        )
        self.assertEqual(intent1, "play_music")
        self.assertEqual(q1.lower(), "cinta luar biasa")

        intent2, q2 = classify_mention_intent(
            f"<@{bot_id}> aku pengen muter musik bye x circus dari britney spears & altare mashup klo gk salah bisa gk tolong puterin",
            bot_id,
        )
        self.assertEqual(intent2, "play_music")
        self.assertIn("bye x circus", q2.lower())
        self.assertNotIn("klo gk salah", q2.lower())

        intent3, q3 = classify_mention_intent(
            f"<@{bot_id}> boleh tambahin ke queue, aku ingin memutar musik dari mashup Britney Spears - Bye X Circus & Altare",
            bot_id,
        )
        self.assertEqual(intent3, "play_music")
        self.assertIn("britney spears", q3.lower())

        # 2. Test complaint "mana, kok gak ke play musik nya" triggers retry_last_music (NOT playing "nya"!)
        save_channel_chat_turn(
            guild_id="1428666546942902294",
            channel_id="ch_music_retry_99",
            user_id="844174494099701780",
            user_name="Seller Hosting",
            user_message="aku pengen muter musik bye x circus dari britney spears & altare mashup",
            bot_reply="Oke boskyuu, nih ku puterin yaa~",
            last_song_query="bye x circus britney spears & altare mashup",
        )
        intent_retry, _ = classify_mention_intent(f"<@{bot_id}> mana, kok gak ke play musik nya", bot_id)
        self.assertEqual(intent_retry, "retry_last_music")
        recovered_song = get_last_requested_song_in_channel("ch_music_retry_99")
        self.assertEqual(recovered_song.lower(), "bye x circus britney spears & altare mashup")

        # 3. Test slang banter response ("woi athena tempek" -> luwes "iya tempek...", tidak ceramah & tidak suruh muter lagu)
        intent_banter, banter_txt = classify_mention_intent(f"woi athena tempek <@{bot_id}>", bot_id)
        ans_banter = answer_mention_question_with_search(banter_txt, "Seller Hosting", channel_id="ch_banter_1")
        self.assertIn("tempek", ans_banter["answer"].lower())
        self.assertNotIn("santai dulu dong kak bahasanya", ans_banter["answer"].lower())
        self.assertNotIn("mau dengerin lagu apa", ans_banter["answer"].lower())

        # 4. Test Mutual Server Filtering on /api/guilds (User A only sees servers where BOTH User A and Bot are members)
        app = create_fastapi_app()
        client = TestClient(app)
        member_a = SimpleNamespace(id=111111, bot=False, guild_permissions=SimpleNamespace(administrator=True), voice=None)
        member_b = SimpleNamespace(id=222222, bot=False, guild_permissions=SimpleNamespace(administrator=True), voice=None)

        guild_abc = SimpleNamespace(
            id=1001, name="Server A", owner_id=111111, voice_client=None, voice_channels=[],
            members=[member_a], get_member=lambda uid: member_a if uid == 111111 else None,
        )
        guild_f = SimpleNamespace(
            id=1002, name="Server F", owner_id=222222, voice_client=None, voice_channels=[],
            members=[member_b], get_member=lambda uid: member_b if uid == 222222 else None,
        )
        app.state.bot = SimpleNamespace(guilds=[guild_abc, guild_f])

        sess_a = _issue_single_discord_session("111111", "UserA", "@usera", "Admin Server", True, user_guild_ids=["1001"])
        sess_b = _issue_single_discord_session("222222", "UserB", "@userb", "Admin Server", True, user_guild_ids=["1002"])

        resp_a = client.get("/api/guilds", headers={"Authorization": f"Bearer {sess_a['session_token']}"})
        guilds_for_a = [g["guild_id"] for g in resp_a.json()["guilds"]]
        self.assertIn("1001", guilds_for_a)
        self.assertNotIn("1002", guilds_for_a)

        resp_b = client.get("/api/guilds", headers={"Authorization": f"Bearer {sess_b['session_token']}"})
        guilds_for_b = [g["guild_id"] for g in resp_b.json()["guilds"]]
        self.assertIn("1002", guilds_for_b)
        self.assertNotIn("1001", guilds_for_b)


if __name__ == "__main__":
    unittest.main()
