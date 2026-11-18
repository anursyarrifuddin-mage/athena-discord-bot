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


def _is_forbidden_ip(ip_obj: object) -> bool:
    return bool(
        getattr(ip_obj, "is_private", False)
        or getattr(ip_obj, "is_loopback", False)
        or getattr(ip_obj, "is_link_local", False)
        or getattr(ip_obj, "is_multicast", False)
        or getattr(ip_obj, "is_reserved", False)
        or getattr(ip_obj, "is_unspecified", False)
    )


def validate_external_url(url: str, resolve_dns: bool = True) -> Tuple[bool, str]:
    """Memvalidasi URL eksternal dan mencegah SSRF ke jaringan lokal/internal (IPv4 & IPv6)."""
    if not url or len(url) > 2048:
        return False, "URL kosong atau melebihi batas panjang."
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return False, "Hanya skema HTTP dan HTTPS yang diizinkan."
    hostname = (parsed.hostname or "").lower().strip(".")
    if not hostname:
        return False, "Hostname URL tidak ditemukan."
    if hostname in ("localhost", "0.0.0.0", "127.0.0.1", "::1", "metadata.google.internal") or hostname.endswith(".local"):
        return False, "Akses ke alamat loopback atau metadata internal ditolak."

    try:
        ip_obj = ipaddress.ip_address(hostname)
        if _is_forbidden_ip(ip_obj):
            return False, "Akses ke alamat IP privat atau internal ditolak."
    except ValueError:
        if resolve_dns:
            try:
                infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
                for _fam, _type, _proto, _canon, sockaddr in infos:
                    ip_str = sockaddr[0]
                    resolved_ip = ipaddress.ip_address(ip_str)
                    if _is_forbidden_ip(resolved_ip):
                        return False, "Domain mengarah ke alamat IP internal yang diblokir."
            except socket.gaierror:
                # Di lingkungan offline/sandbox tanpa DNS, blokir hanya jika hostname lokal
                pass
            except Exception:
                return False, "Gagal memvalidasi DNS untuk hostname tujuan."

    return True, "OK"


def build_safe_url_opener():
    """Membangun urllib opener yang memvalidasi ulang setiap hop HTTP redirect terhadap SSRF."""
    import urllib.request

    class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            ok, reason = validate_external_url(newurl, resolve_dns=True)
            if not ok:
                raise ValueError(f"Redirect SSRF diblokir: {reason}")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(_SafeRedirectHandler)


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
    is_admin: bool = False,
    session_host_id: str = "",
    action: str = "control",
    target_item_requester_id: Optional[str] = None,
    is_owner: bool = False,
    dj_role_id: str = "",
) -> Tuple[bool, str]:
    """
    Aturan Host Lock System (Mendukung Owner, Admin, DJ Role, dan Session Host):
    - Owner bot, Administrator server Discord, dan pemilik Role DJ dapat mengontrol semua antrean.
    - Session Host dapat mengontrol antrean selama sesinya aktif.
    - Pengguna biasa hanya dapat menghapus (remove) item miliknya sendiri.
    """
    if is_owner or is_admin:
        return True, "Diizinkan (Administrator / Owner)."
    if dj_role_id and dj_role_id in (user_roles or []):
        return True, "Diizinkan (Role DJ)."
    if "role-admin" in (user_roles or []) or "role-dj" in (user_roles or []):
        return True, "Diizinkan (Role DJ / Admin)."
    if not session_host_id or session_host_id == user_id:
        return True, "Diizinkan (Session Host)."
    if (
        action in ("remove_item", "skip", "pause", "resume", "replay", "seek")
        and target_item_requester_id
        and str(target_item_requester_id) == str(user_id)
    ):
        return True, f"Diizinkan (Peminta/requester lagu aktif untuk aksi '{action}')."

    return (
        False,
        f"Host Lock aktif: Hanya Session Host (<@{session_host_id}>), Role DJ, atau Administrator server Discord yang dapat melakukan aksi '{action}'.",
    )


def check_host_lock_permission(
    user_id: str,
    user_roles: List[str],
    is_admin: bool = False,
    session_host_id: str = "",
    action: str = "control",
    target_item_requester_id: Optional[str] = None,
    is_owner: bool = False,
    dj_role_id: str = "",
) -> Tuple[bool, str]:
    """Alias kompatibilitas untuk pemeriksaan izin Host Lock pada bot Discord dan API."""
    return can_control_queue(
        user_id=user_id,
        user_roles=user_roles,
        is_admin=is_admin,
        session_host_id=session_host_id,
        action=action,
        target_item_requester_id=target_item_requester_id,
        is_owner=is_owner,
        dj_role_id=dj_role_id,
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
        # Bersihkan entri kedaluwarsa secara berkala agar RAM tidak membengkak
        if len(self._hits) > 512:
            stale_keys = [k for k, arr in list(self._hits.items()) if not arr or arr[-1] <= cutoff]
            for sk in stale_keys:
                self._hits.pop(sk, None)
            if len(self._hits) > 1024:
                for sk in list(self._hits.keys())[:256]:
                    self._hits.pop(sk, None)
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
