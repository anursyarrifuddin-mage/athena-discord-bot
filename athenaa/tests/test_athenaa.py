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
DTEND:20261115T165900Z
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
        from app.services.music_service import extract_spotify_playlist_tracks

        self.assertEqual(
            classify_music_input("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC")[0],
            "spotify_track",
        )
        self.assertEqual(
            classify_music_input("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")[0],
            "spotify_playlist",
        )
        self.assertEqual(
            classify_music_input("https://open.spotify.com/album/1ATL5GLyefJaxhQzSPVrLX")[0],
            "spotify_album",
        )
        self.assertEqual(
            classify_music_input("https://www.youtube.com/playlist?list=PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI")[0],
            "youtube_playlist",
        )
        self.assertEqual(
            classify_music_input("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI")[0],
            "youtube_playlist",
        )
        self.assertEqual(
            classify_music_input("https://www.youtube.com/watch?v=dQw4w9WgXcQ")[0],
            "youtube",
        )
        self.assertEqual(classify_music_input("Hindia Evaluasi")[0], "search_query")

        # Verify direct playlist extraction returns tracks for both Spotify & YouTube playlists
        yt_pl = extract_spotify_playlist_tracks(
            "https://www.youtube.com/playlist?list=PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI",
            max_tracks=10,
        )
        self.assertGreater(len(yt_pl.get("tracks") or []), 0)

        # Verify favorites and saved playlists tables are removed from SQLite
        with self.db.transaction() as conn:
            tables = {
                r["name"]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
        self.assertNotIn("favorites", tables)
        self.assertNotIn("playlists", tables)
        self.assertNotIn("playlist_items", tables)

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
            actor_id="user-dj",
            user_roles=["role-dj"],
            dj_role_id="role-dj",
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
        self.assertTrue(st.autoplay)
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
            is_owner=True,
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
            is_owner=True,
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

    def test_per_server_3role_rbac_and_hidden_codebase(self) -> None:
        import asyncio
        from app.web.routes.api import (
            _get_session_from_token,
            _issue_single_discord_session,
            _resolve_role_for_guild,
            _resolve_static_dir,
        )
        from app.bot.client import build_discord_bot

        # 1. Issue session as Admin Server on Server A (111111111111111111)
        issued = _issue_single_discord_session(
            user_id="u-admin-server-a",
            username="AdminA",
            discord_tag="@admina",
            role_label="Admin Server",
            is_owner=False,
            has_dj_role=True,
            is_admin=True,
            guild_id="111111111111111111",
        )
        tok = issued["session_token"]
        self.assertEqual(issued["user"]["role"], "admin")
        self.assertTrue(issued["user"]["isAdmin"])
        self.assertFalse(issued["user"]["isOwner"])

        # 2. On Server A (111111111111111111), user resolves to Admin Server
        sess_a = _get_session_from_token(tok, guild_id="111111111111111111")
        self.assertIsNotNone(sess_a)
        self.assertEqual(sess_a["user"]["role"], "admin")
        self.assertTrue(sess_a["user"]["isAdmin"])
        self.assertTrue(sess_a["user"]["hasDjRole"])
        self.assertFalse(sess_a["user"]["isOwner"])

        # 3. On Server B (222222222222222222), the same user is strictly a regular Member!
        sess_b = _get_session_from_token(tok, guild_id="222222222222222222")
        self.assertIsNotNone(sess_b)
        self.assertEqual(sess_b["user"]["role"], "member")
        self.assertFalse(sess_b["user"]["isAdmin"])
        self.assertFalse(sess_b["user"]["hasDjRole"])
        self.assertFalse(sess_b["user"]["isOwner"])
        self.assertEqual(
            _resolve_role_for_guild("u-admin-server-a", "222222222222222222", default_main_role="admin"),
            "member",
        )

        # 4. Verify pre-built static UI directory resolves and index.html exists
        static_dir = _resolve_static_dir()
        self.assertTrue((static_dir / "index.html").exists())

        # 5. Verify MusicPlayerControlView initializes cleanly with all 12 Discord embed buttons
        bot = build_discord_bot(queue_service=self.queue_svc, academy_service=self.academy_svc)

        async def _build_view():
            v = bot.create_player_control_view("111111111111111111")
            return len(v.children)

        btn_count = asyncio.run(_build_view())
        self.assertEqual(btn_count, 12)

    def test_version_aware_music_matching_and_module_delete(self) -> None:
        from app.services.music_service import (
            _clean_youtube_title_and_artist,
            _extract_vid_from_url_or_registry,
            _register_track_meta,
            detect_version_modifiers,
            do_version_modifiers_match,
            normalize_exact_version_identity,
        )

        # 1. Version modifiers detection & strict matching
        normal_mods = detect_version_modifiers("the weeknd - one of the girls")
        dj_mods = detect_version_modifiers("DJ One Of The Girls Remix Full Bass")
        slowed_mods = detect_version_modifiers("One Of The Girls (Slowed + Reverb)")
        self.assertEqual(normal_mods, set())
        self.assertTrue({"dj", "remix"}.issubset(dj_mods))
        self.assertIn("slowed", slowed_mods)

        self.assertTrue(do_version_modifiers_match(normal_mods, set()))
        self.assertFalse(do_version_modifiers_match(normal_mods, dj_mods))
        self.assertFalse(do_version_modifiers_match(normal_mods, slowed_mods))
        self.assertFalse(do_version_modifiers_match(dj_mods, set()))
        self.assertTrue(do_version_modifiers_match(dj_mods, dj_mods))

        # 2. Title cleaner preserves DJ/Remix/Slowed inside brackets/pipes while removing Official Audio junk
        t_orig, a_orig = _clean_youtube_title_and_artist(
            "The Weeknd - One Of The Girls (Official Audio)", "The Weeknd - Topic"
        )
        self.assertEqual(t_orig, "One Of The Girls")
        self.assertEqual(a_orig, "The Weeknd")

        t_dj, a_dj = _clean_youtube_title_and_artist(
            "The Weeknd - One Of The Girls (DJ Remix Official Audio)", "DJ Opus"
        )
        self.assertIn("DJ", t_dj)
        self.assertIn("Remix", t_dj)
        self.assertNotIn("Official Audio", t_dj)

        # 3. _TRACK_META_REGISTRY separates original song from DJ/Remix version (never overwrites!)
        self.assertNotEqual(
            normalize_exact_version_identity(t_orig, a_orig),
            normalize_exact_version_identity(t_dj, a_dj),
        )
        _register_track_meta(
            t_orig, a_orig, 244, "https://www.youtube.com/watch?v=ORIG1234567", video_id="ORIG1234567", allow_overwrite=True
        )
        _register_track_meta(
            t_dj, a_dj, 210, "https://www.youtube.com/watch?v=DJRMX123456", video_id="DJRMX123456", allow_overwrite=True
        )
        self.assertEqual(_extract_vid_from_url_or_registry("", title=t_orig, artist=a_orig), "ORIG1234567")
        self.assertEqual(_extract_vid_from_url_or_registry("", title=t_dj, artist=a_dj), "DJRMX123456")

        # 4. Module / attachment deletion removes DB row and stored file
        guild_id = "1428666546942902294"
        task = self.academy_svc.create_task(
            guild_id=guild_id,
            course_name="IF3130 Jaringan Komputer",
            title="Tugas Modul Jarkom",
            deadline_iso="2026-11-25T16:59:00+00:00",
        )
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO task_attachments (
                    attachment_id, task_id, guild_id, original_filename,
                    stored_filename, mime_type, size_bytes, uploaded_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "att-testdel01",
                    task.task_id,
                    guild_id,
                    "Modul_Jarkom_Bab1.pdf",
                    "0123456789abcdef0123456789abcdef.pdf",
                    "application/pdf",
                    4096,
                    "Aetheriaaa",
                    "2026-11-08T00:00:00+00:00",
                ),
            )
        deleted = self.academy_svc.delete_attachment(guild_id, "att-testdel01")
        self.assertIsNotNone(deleted)
        self.assertEqual(deleted["original_filename"], "Modul_Jarkom_Bab1.pdf")
        self.assertIsNone(self.academy_svc.delete_attachment(guild_id, "att-testdel01"))

<<<<<<< HEAD
    def test_security_hardening_strict_voice_follow_and_oauth_state(self) -> None:
        import asyncio
        from types import SimpleNamespace
        from app.bot.client import build_discord_bot
        from app.security.validators import (
            generate_oauth_state,
            sanitize_discord_outbound_text,
            verify_oauth_state,
        )
        from app.web.routes.api import _get_session_from_token

        # 1. OAuth2 CSRF state HMAC generation & verification
        secret = "test-hmac-secret-key-2026"
        state_tok = generate_oauth_state(secret)
        self.assertTrue(verify_oauth_state(state_tok, secret))
        self.assertFalse(verify_oauth_state(state_tok + "tampered", secret))
        self.assertFalse(verify_oauth_state("", secret))

        # 2. Anti-Scam / Anti-Raid outbound text sanitizer
        clean = sanitize_discord_outbound_text("Halo @everyone dan @here cek <@&123456789> free crypto mrbeast giveaway")
        self.assertNotIn("@everyone", clean)
        self.assertNotIn("@here", clean)
        self.assertNotIn("<@&123456789>", clean)
        self.assertIn("[diblokir-keamanan]", clean)

        # 3. Empty token never auto-logs in
        self.assertIsNone(_get_session_from_token("", guild_id="1428666546942902294"))

        # 4. Strict Voice Channel Following:
        # User A (111111) is in Voice Channel "Ruang Musik", User B (222222) is NOT in any Voice Channel.
        # When User B triggers playback from Web Player (requester_user_id="222222"),
        # the bot MUST NOT join User A's voice channel!
        bot = build_discord_bot(queue_service=self.queue_svc, academy_service=self.academy_svc)
        user_a = SimpleNamespace(id=111111, bot=False, display_name="UserA")
        vc_room = SimpleNamespace(id=999888777, name="Ruang Musik", members=[user_a])
        user_a.voice = SimpleNamespace(channel=vc_room)
        user_b = SimpleNamespace(id=222222, bot=False, display_name="UserB", voice=None)

        fake_guild = SimpleNamespace(
            id=1428666546942902294,
            name="Server Multi",
            voice_client=None,
            voice_channels=[vc_room],
            get_member=lambda uid: user_a if uid == 111111 else (user_b if uid == 222222 else None),
            get_channel=lambda cid: vc_room if cid == 999888777 else None,
        )
        bot.get_guild = lambda gid: fake_guild if gid == 1428666546942902294 else None

        vc_for_user_b = asyncio.run(
            bot.ensure_voice_connected("1428666546942902294", requester_user_id="222222")
        )
        self.assertIsNone(vc_for_user_b)

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006

if __name__ == "__main__":
    unittest.main()






<<<<<<< HEAD

=======
>>>>>>> 2439a1311dd6e8ff3e51349083f726bff9305006
