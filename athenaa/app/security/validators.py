"""
Modul Keamanan Aplikasi:
- Validasi Host Lock (Session Host, DJ Role, Server Admin, Owner)
- Pencegahan SSRF (memblokir localhost/private IP untuk input URL eksternal)
- Pencegahan Path Traversal & validasi file modul (.pdf, .doc, .docx, maks 15 MB, magic bytes)
- Enkripsi simetris kredensial integrasi & penyamaran token untuk log
- Validasi state OAuth2, token CSRF, dan Rate Limiter berbasis sliding window
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import re
import socket
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".vbs", ".js", ".jar", ".msi", ".php", ".py", ".dll", ".elf"
}

MAGIC_SIGNATURES = {
    ".pdf": [b"%PDF-"],
    ".doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],  # Compound File Binary Format (OLE2)
    ".docx": [b"PK\x03\x04"],  # OpenXML ZIP container
}


def mask_secret(value: str) -> str:
    """Menyamarkan token atau secret sebelum ditulis ke log."""
    if not value or len(value) < 8:
        return "***"
    return f"{value[:3]}...{value[-3:]}"


def encrypt_secret(plaintext: str, key: str) -> str:
    """Enkripsi kredensial sensitif (misal URL .ics ber-token) dengan stream key SHA-256 + HMAC."""
    if not plaintext:
        return ""
    raw = plaintext.encode("utf-8")
    nonce = os.urandom(16)
    key_bytes = hashlib.sha256(key.encode("utf-8")).digest()
    stream = b"".join(
        hashlib.sha256(key_bytes + nonce + i.to_bytes(4, "big")).digest()
        for i in range((len(raw) // 32) + 1)
    )[: len(raw)]
    cipher = bytes(a ^ b for a, b in zip(raw, stream))
    mac = hmac.new(key_bytes, nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")


def decrypt_secret(token: str, key: str) -> str:
    """Dekripsi kredensial dan verifikasi integritas HMAC."""
    if not token:
        return ""
    data = base64.urlsafe_b64decode(token.encode("ascii"))
    if len(data) < 48:
        raise ValueError("Format token terenkripsi tidak valid.")
    nonce, mac, cipher = data[:16], data[16:48], data[48:]
    key_bytes = hashlib.sha256(key.encode("utf-8")).digest()
    expected_mac = hmac.new(key_bytes, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("Integritas token terenkripsi gagal diverifikasi.")
    stream = b"".join(
        hashlib.sha256(key_bytes + nonce + i.to_bytes(4, "big")).digest()
        for i in range((len(cipher) // 32) + 1)
    )[: len(cipher)]
    plain = bytes(a ^ b for a, b in zip(cipher, stream))
    return plain.decode("utf-8")


def validate_external_url(url: str, resolve_dns: bool = False) -> Tuple[bool, str]:
    """Memvalidasi URL eksternal dan mencegah SSRF ke jaringan lokal/internal."""
    if not url or len(url) > 2048:
        return False, "URL kosong atau melebihi batas panjang."
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return False, "Hanya skema HTTP dan HTTPS yang diizinkan."
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "Hostname URL tidak ditemukan."
    if hostname in ("localhost", "0.0.0.0", "127.0.0.1", "::1", "metadata.google.internal"):
        return False, "Akses ke alamat loopback atau metadata internal ditolak."

    try:
        ip_obj = ipaddress.ip_address(hostname)
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
        ):
            return False, "Akses ke alamat IP privat atau internal ditolak."
    except ValueError:
        if resolve_dns:
            try:
                resolved_ip = ipaddress.ip_address(socket.gethostbyname(hostname))
                if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local:
                    return False, "Domain mengarah ke alamat IP internal yang diblokir."
            except Exception:
                return False, "Gagal memvalidasi DNS untuk hostname tujuan."

    return True, "OK"


def sanitize_and_validate_attachment(
    filename: str,
    content_bytes: bytes,
    max_mb: int = 15,
) -> Tuple[bool, str, str]:
    """
    Memvalidasi lampiran modul akademik:
    - Mencegah path traversal (.., /, \\)
    - Memeriksa ukuran maksimum (default 15 MB)
    - Memeriksa allowlist ekstensi (.pdf, .doc, .docx)
    - Memeriksa signature magic bytes file
    - Menghasilkan nama file internal berbasis UUID yang aman
    """
    if not filename or "\x00" in filename:
        return False, "Nama file tidak valid.", ""

    if ".." in filename or "/" in filename or "\\" in filename:
        return False, "Terdeteksi percobaan path traversal pada nama file.", ""

    clean_name = Path(filename).name
    ext = Path(clean_name).suffix.lower()

    if ext in BLOCKED_EXTENSIONS or ext not in ALLOWED_EXTENSIONS:
        return False, f"Ekstensi '{ext}' ditolak. Hanya .pdf, .doc, dan .docx yang diizinkan.", ""

    max_bytes = max_mb * 1024 * 1024
    if len(content_bytes) == 0:
        return False, "File kosong tidak diizinkan.", ""
    if len(content_bytes) > max_bytes:
        return False, f"Ukuran file melebihi batas maksimum {max_mb} MB.", ""

    valid_sigs = MAGIC_SIGNATURES.get(ext, [])
    if valid_sigs and not any(content_bytes.startswith(sig) for sig in valid_sigs):
        return False, f"Signature isi file tidak sesuai dengan format {ext}.", ""

    safe_stored_name = f"{uuid.uuid4().hex}{ext}"
    return True, "OK", safe_stored_name


def can_control_queue(
    user_id: str,
    user_roles: List[str],
    is_admin: bool,
    is_owner: bool,
    session_host_id: str,
    dj_role_id: str,
    action: str = "control",
    target_item_requester_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Aturan Host Lock System:
    - Owner bot, Administrator server, dan pemilik Role DJ dapat mengontrol semua antrean.
    - Session Host dapat mengontrol antrean selama sesinya aktif.
    - Pengguna biasa hanya dapat menghapus (remove) item miliknya sendiri.
    - Pengguna biasa tidak dapat skip, stop, shuffle, atau menghapus lagu pengguna lain.
    """
    if is_owner or is_admin:
        return True, "Diizinkan (Administrator / Owner)."
    if dj_role_id and dj_role_id in user_roles:
        return True, "Diizinkan (Role DJ)."
    if not session_host_id or session_host_id == user_id:
        return True, "Diizinkan (Session Host)."
    if action == "remove_item" and target_item_requester_id and target_item_requester_id == user_id:
        return True, "Diizinkan (Menghapus lagu milik sendiri)."

    return (
        False,
        f"Host Lock aktif: Hanya Session Host (<@{session_host_id}>), Role DJ, atau Admin yang dapat melakukan aksi '{action}'.",
    )


def check_host_lock_permission(
    user_id: str,
    user_roles: List[str],
    is_admin: bool,
    is_owner: bool,
    session_host_id: str,
    dj_role_id: str,
    action: str = "control",
    target_item_requester_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """Alias kompatibilitas untuk pemeriksaan izin Host Lock pada bot Discord dan API."""
    return can_control_queue(
        user_id=user_id,
        user_roles=user_roles,
        is_admin=is_admin,
        is_owner=is_owner,
        session_host_id=session_host_id,
        dj_role_id=dj_role_id,
        action=action,
        target_item_requester_id=target_item_requester_id,
    )



class SlidingWindowRateLimiter:
    """Rate limiter dasar berbasis sliding window per kunci (IP / User ID)."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, List[float]] = {}

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        current = now if now is not None else time.time()
        cutoff = current - self.window_seconds
        history = [ts for ts in self._hits.get(key, []) if ts > cutoff]
        if len(history) >= self.max_requests:
            self._hits[key] = history
            return False
        history.append(current)
        self._hits[key] = history
        return True


DISCORD_SNOWFLAKE_RE = re.compile(r"^\d{15,22}$")


def is_valid_snowflake(value: str) -> bool:
    return bool(DISCORD_SNOWFLAKE_RE.match(value.strip()))
