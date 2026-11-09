"""
Jembatan CLI Eksekusi Python Nyata untuk Web Server Port 3000:
Memungkinkan dashboard mengeksekusi langsung modul Python Athenaa:
- Pembuatan snapshot backup SQLite terenkripsi (BackupService)
- Pembuatan bundel kode sumber lengkap athenaa-discord-bot.zip (siap Unarchive di /home/container Pterodactyl)
- Eksekusi suite pengujian otomatis unittest secara live
"""

from __future__ import annotations

import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

from app.config import BASE_DIR, settings
from app.services.backup_service import BackupService


def create_source_zip() -> str:
    zip_path = settings.backups_dir / "athenaa-discord-bot.zip"
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in BASE_DIR.rglob("*"):
            if file_path.is_dir():
                continue
            rel = file_path.relative_to(BASE_DIR)
            rel_str = str(rel)
            if (
                "__pycache__" in rel_str
                or rel_str.endswith(".pyc")
                or rel_str.endswith(".db")
                or rel_str.endswith(".enc")
                or rel_str.endswith(".zip")
            ):
                continue
            # Tulis langsung di root arsip agar saat Unarchive di /home/container Pterodactyl
            # struktur app/main.py dan requirements.txt langsung berada di /home/container/
            zf.write(file_path, rel_str)
        if not (BASE_DIR / ".env.example").exists():
            env_example = BASE_DIR.parent / ".env.example"
            if env_example.exists():
                zf.write(env_example, ".env.example")
    return str(zip_path)


def run_test_suite() -> dict:
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(BASE_DIR / "tests"), pattern="test_*.py")
    buf = io.StringIO()
    runner = unittest.TextTestRunner(stream=buf, verbosity=2)
    result = runner.run(suite)
    return {
        "ran": result.testsRun,
        "passed": result.wasSuccessful(),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "output": buf.getvalue(),
    }


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "backup":
        svc = BackupService()
        print(json.dumps(svc.create_consistent_backup(encrypt=True)))
    elif cmd == "ytdlp":
        update_flag = "--update" in sys.argv
        print(json.dumps(BackupService.check_and_update_ytdlp(perform_update=update_flag)))
    elif cmd == "zip":
        path = create_source_zip()
        print(json.dumps({"success": True, "zip_path": path}))
    elif cmd == "test":
        print(json.dumps(run_test_suite()))
    else:
        print(json.dumps({"status": "ready", "version": "1.0.0"}))


if __name__ == "__main__":
    main()
