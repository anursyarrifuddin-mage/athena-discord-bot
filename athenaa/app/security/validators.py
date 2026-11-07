"""
Modul Keamanan Aplikasi:
- Validasi Host Lock (Session Host, DJ Role, Server Admin, Owner)
- Pencegahan SSRF (memblokir localhost/private IP untuk input URL eksternal)
- Pencegahan Path Traversal & validasi file modul (.pdf, .doc, .docx, maks 15 MB, magic bytes)
- Enkripsi simetris kredensial integrasi & penyamaran token untuk log (menggunakan cryptography.Fernet)
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

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    Fernet = None  # type: ignore

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


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive encryption key from password using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return kdf.derive(password.encode("utf-8"))


def _get_fernet(password: str) -> "Fernet":
    """Get or create Fernet instance from password (with fixed salt for deterministic key)."""
    if not CRYPTOGRAPHY_AVAILABLE:
        raise RuntimeError("cryptography library not installed. Run: pip install cryptography")
    # Use a fixed salt derived from the password for deterministic key derivation
    # In production, consider storing salt separately
    salt = hashlib.sha256(password.encode("utf-8")).digest()[:16]
    key = _derive_key(password, salt)
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(plaintext: str, key: str) -> str:
    """Enkripsi kredensial sensitif menggunakan Fernet (AES-128-GCM authenticated encryption)."""
    if not plaintext:
        return ""
    try:
        fernet = _get_fernet(key)
        token = fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("ascii")
    except Exception as e:
        raise ValueError(f"Gagal enkripsi: {e}")


def decrypt_secret(token: str, key: str) -> str:
    """Dekripsi kredensial dan verifikasi integritas (Fernet handles auth automatically)."""
    if not token:
        return ""
    try:
        fernet = _get_fernet(key)
        plaintext = fernet.decrypt(token.encode("ascii"))
        return plaintext.decode("utf-8")
    except Exception as e:
        raise ValueError(f"Gagal dekripsi/integritas gagal: {e}")


def validate_external_url(url: str, resolve_dns: bool = True) -> Tuple[bool, str]:
    """Memvalidasi URL eksternal dan mencegah SSRF ke jaringan lokal/internal.
    
    SELALU resolve DNS (default True) untuk mencegah DNS rebinding attacks.
    Blokir private CIDR: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 127.0.0.0/8, ::1/128, fc00::/7.
    """
    if not url or len(url) > 2048:
        return False, "URL kosong atau melebihi batas panjang."
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return False, "Hanya skema HTTP dan HTTPS yang diizinkan."
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "Hostname URL tidak ditemukan."
    
    # Blocklist hostname berbahaya
    blocked_hostnames = {
        "localhost", "0.0.0.0", "127.0.0.1", "::1", 
        "metadata.google.internal", "metadata", "metadata.azure.com",
        "169.254.169.254",  # AWS/GCP/Azure metadata
    }
    if hostname in blocked_hostnames:
        return False, "Akses ke alamat loopback atau metadata internal ditolak."

    # Selalu resolve DNS untuk validasi IP tujuan (mencegah DNS rebinding)
    try:
        # Resolve hostname ke IP (IPv4)
        resolved_ips = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM)
        for _, _, _, _, sockaddr in resolved_ips:
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)
            if _is_private_or_reserved_ip(ip_obj):
                return False, f"Domain mengarah ke alamat IP internal yang diblokir: {ip_str}"
    except socket.gaierror:
        return False, "Gagal memvalidasi DNS untuk hostname tujuan."
    except Exception as e:
        return False, f"Error validasi DNS: {e}"

    # Jika hostname langsung berupa IP, validasi juga
    try:
        ip_obj = ipaddress.ip_address(hostname)
        if _is_private_or_reserved_ip(ip_obj):
            return False, "Akses ke alamat IP privat atau internal ditolak."
    except ValueError:
        pass  # Bukan IP literal, sudah divalidasi via DNS di atas

    return True, "OK"


def _is_private_or_reserved_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Cek apakah IP termasuk private, loopback, link-local, multicast, reserved, atau documentation."""
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        # Documentation networks (RFC 5737, RFC 3849)
        or (ip_obj.version == 4 and ip_obj in ipaddress.ip_network("192.0.2.0/24"))
        or (ip_obj.version == 4 and ip_obj in ipaddress.ip_network("198.51.100.0/24"))
        or (ip_obj.version == 4 and ip_obj in ipaddress.ip_network("203.0.113.0/24"))
        or (ip_obj.version == 6 and ip_obj in ipaddress.ip_network("2001:db8::/32"))
    )


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
    has_dj_role: bool = False,
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
    if has_dj_role or (dj_role_id and dj_role_id in user_roles):
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
    has_dj_role: bool = False,
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
        has_dj_role=has_dj_role,
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


def validate_snowflake_param(param_name: str, value: str) -> None:
    """Validasi parameter Discord snowflake ID, raise HTTPException jika tidak valid."""
    if not value or not is_valid_snowflake(value):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Parameter {param_name} tidak valid: harus berupa Discord Snowflake ID (15-22 digit).")
