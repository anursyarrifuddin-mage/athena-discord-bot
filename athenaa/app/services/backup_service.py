"""
Modul Super-Admin: Backup Database SQLite Aman & Kontrol Worker yt-dlp.
- Menggunakan sqlite3Connection.backup() untuk snapshot konsisten tanpa risiko korup.
- Mengompresi dengan gzip dan mengenkripsi backup dengan Fernet (AES-128-GCM authenticated encryption).
- Memeriksa batas ukuran lampiran Discord sebelum pengiriman DM dan menyimpan salinan lokal jika gagal.
"""

from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from app.config import settings
from app.security.validators import encrypt_secret, decrypt_secret


class BackupService:
    """Layanan pembuatan backup SQLite aman, terkompresi, dan terenkripsi."""

    def __init__(self, db_path: Optional[Path] = None, backup_dir: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else settings.sqlite_path
        self.backup_dir = Path(backup_dir) if backup_dir else settings.backups_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_consistent_backup(self, encrypt: bool = True) -> Dict[str, str | int | bool]:
        """
        Membuat snapshot SQLite konsisten menggunakan online backup API,
        mengompresi dengan gzip, dan mengenkripsi dengan Fernet (AES-128-GCM).
        File sementara dibersihkan dengan aman di blok finally.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        temp_snapshot = self.backup_dir / f"temp_snapshot_{timestamp}.sqlite"
        final_ext = ".sqlite.gz.enc" if encrypt else ".sqlite.gz"
        final_path = self.backup_dir / f"athenaa_backup_{timestamp}{final_ext}"

        try:
            src_conn = sqlite3.connect(str(self.db_path))
            dst_conn = sqlite3.connect(str(temp_snapshot))
            try:
                with dst_conn:
                    src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
                src_conn.close()

            raw_bytes = temp_snapshot.read_bytes()
            compressed = gzip.compress(raw_bytes, compresslevel=6)

            if encrypt:
                # Use Fernet encryption (AES-128-GCM authenticated encryption)
                payload = encrypt_secret(compressed, settings.backup_encryption_key).encode("ascii")
            else:
                payload = compressed

            final_path.write_bytes(payload)
            size_bytes = final_path.stat().st_size
            can_send_dm = size_bytes <= (8 * 1024 * 1024)

            return {
                "success": True,
                "filename": final_path.name,
                "path": str(final_path),
                "size_bytes": size_bytes,
                "encrypted": encrypt,
                "can_send_discord_dm": can_send_dm,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            if temp_snapshot.exists():
                try:
                    temp_snapshot.unlink()
                except OSError:
                    pass

    @staticmethod
    def check_and_update_ytdlp(perform_update: bool = False) -> Dict[str, str | bool]:
        """
        Memeriksa versi yt-dlp pada subprocess terisolasi dan menjalankan pembaruan terkontrol
        apabila perform_update=True dan pip tersedia di lingkungan hosting.
        """
        ytdlp_bin = shutil.which("yt-dlp")
        current_version = "Belum terinstal di PATH kontainer"
        if ytdlp_bin:
            proc = subprocess.run([ytdlp_bin, "--version"], capture_output=True, text=True, timeout=10, check=False)
            if proc.returncode == 0:
                current_version = proc.stdout.strip()

        if not perform_update:
            return {
                "installed": bool(ytdlp_bin),
                "current_version": current_version,
                "updated": False,
                "message": "Pemeriksaan versi yt-dlp selesai.",
            }

        pip_check = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if pip_check.returncode != 0:
            return {
                "installed": bool(ytdlp_bin),
                "current_version": current_version,
                "updated": False,
                "message": (
                    "Modul pip tidak tersedia pada kontainer ini sehingga paket yt-dlp tidak dapat diperbarui "
                    "secara otomatis saat runtime. Perbarui melalui image kontainer atau pasang python3-pip."
                ),
            }

        up_proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if up_proc.returncode != 0:
            return {
                "installed": bool(ytdlp_bin),
                "current_version": current_version,
                "updated": False,
                "message": f"Pembaruan yt-dlp gagal: {up_proc.stderr.strip()[:200]}",
            }

        new_version = current_version
        ytdlp_bin_after = shutil.which("yt-dlp")
        if ytdlp_bin_after:
            v_proc = subprocess.run([ytdlp_bin_after, "--version"], capture_output=True, text=True, timeout=10, check=False)
            if v_proc.returncode == 0:
                new_version = v_proc.stdout.strip()

        return {
            "installed": True,
            "current_version": new_version,
            "updated": True,
            "message": f"Worker subprocess yt-dlp berhasil diperbarui dari {current_version} ke {new_version}.",
        }
