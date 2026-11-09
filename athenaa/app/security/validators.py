"""
Modul Keamanan Aplikasi:
- Validasi Host Lock Per-Server (Admin Server, Role DJ, dan Member / Session Host)
- Pencegahan SSRF (memblokir localhost/private IP untuk input URL eksternal)
- Pencegahan Path Traversal & validasi file modul (.pdf, .doc, .docx, maks 15 MB, magic bytes)
- Enkripsi simetris kredensial integrasi & penyamaran token untuk log (Fernet + stdlib HMAC fallback)
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
    if CRYPTOGRAPHY_AVAILABLE:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        return kdf.derive(password.encode("utf-8"))
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000, dklen=32)


def _get_fernet(password: str) -> "Fernet":
    """Get or create Fernet instance from password (with fixed salt for deterministic key)."""
    salt = hashlib.sha256(password.encode("utf-8")).digest()[:16]
    key = _derive_key(password, salt)
    return Fernet(base64.urlsafe_b64encode(key))


def _stdlib_encrypt(raw_bytes: bytes, key_str: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", key_str.encode("utf-8"), salt, 50_000, dklen=64)
    enc_key, mac_key = derived[:32], derived[32:]
    out = bytearray(len(raw_bytes))
    for i in range(0, len(raw_bytes), 32):
        blk = hashlib.sha256(enc_key + salt + i.to_bytes(8, "big")).digest()
        chunk = raw_bytes[i : i + 32]
        for j, b in enumerate(chunk):
            out[i + j] = b ^ blk[j]
    cipher_bytes = bytes(out)
    tag = hmac.new(mac_key, salt + cipher_bytes, hashlib.sha256).digest()
    return "STD1$" + base64.urlsafe_b64encode(salt + tag + cipher_bytes).decode("ascii")


def _stdlib_decrypt(token: str, key_str: str) -> bytes:
    payload = base64.urlsafe_b64decode(token[5:].encode("ascii"))
    if len(payload) < 48:
        raise ValueError("Token terenkripsi rusak.")
    salt = payload[:16]
    tag = payload[16:48]
    cipher_bytes = payload[48:]
    derived = hashlib.pbkdf2_hmac("sha256", key_str.encode("utf-8"), salt, 50_000, dklen=64)
    enc_key, mac_key = derived[:32], derived[32:]
    expected_tag = hmac.new(mac_key, salt + cipher_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("Integritas HMAC gagal.")
    out = bytearray(len(cipher_bytes))
    for i in range(0, len(cipher_bytes), 32):
        blk = hashlib.sha256(enc_key + salt + i.to_bytes(8, "big")).digest()
        chunk = cipher_bytes[i : i + 32]
        for j, b in enumerate(chunk):
            out[i + j] = b ^ blk[j]
    return bytes(out)


def encrypt_secret(plaintext: str | bytes, key: str = "") -> str:
    """Enkripsi kredensial sensitif menggunakan Fernet atau stdlib PBKDF2+HMAC fallback."""
    if not plaintext:
        return ""
    eff_key = key or os.getenv("ENCRYPTION_KEY", "athenaa-default-encryption-key-2026")
    raw_bytes = plaintext.encode("utf-8") if isinstance(plaintext, str) else bytes(plaintext)
    if CRYPTOGRAPHY_AVAILABLE:
        try:
            fernet = _get_fernet(eff_key)
            token = fernet.encrypt(raw_bytes)
            return token.decode("ascii")
        except Exception as e:
            raise ValueError(f"Gagal enkripsi: {e}")
    return _stdlib_encrypt(raw_bytes, eff_key)


def decrypt_secret(token: str, key: str = "") -> str:
    """Dekripsi kredensial dan verifikasi integritas."""
    if not token:
        return ""
    eff_key = key or os.getenv("ENCRYPTION_KEY", "athenaa-default-encryption-key-2026")
    if token.startswith("STD1$"):
        raw = _stdlib_decrypt(token, eff_key)
        return raw.decode("utf-8", errors="replace")
    if CRYPTOGRAPHY_AVAILABLE:
        try:
            fernet = _get_fernet(eff_key)
            plaintext = fernet.decrypt(token.encode("ascii"))
            return plaintext.decode("utf-8", errors="replace")
        except Exception as e:
            raise ValueError(f"Gagal dekripsi/integritas gagal: {e}")
    raise ValueError("Format token membutuhkan pustaka cryptography.")


def validate_external_url(url: str, resolve_dns: bool = True) -> Tuple[bool, str]:
    """Memvalidasi URL eksternal dan mencegah SSRF ke jaringan lokal/internal."""
    if not url or len(url) > 2048:
        return False, "URL kosong atau melebihi batas panjang."
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return False, "Hanya skema HTTP dan HTTPS yang diizinkan."
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "Hostname URL tidak ditemukan."

    blocked_hostnames = {
        "localhost",
        "0.0.0.0",
        "127.0.0.1",
        "::1",
        "metadata.google.internal",
        "metadata",
        "metadata.azure.com",
        "169.254.169.254",
    }
    if hostname in blocked_hostnames:
        return False, "Akses ke alamat loopback atau metadata internal ditolak."

    try:
        ip_obj = ipaddress.ip_address(hostname)
        if _is_private_or_reserved_ip(ip_obj):
            return False, "Akses ke alamat IP privat atau internal ditolak."
    except ValueError:
        if resolve_dns:
            try:
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

    return True, "OK"


def _is_private_or_reserved_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Cek apakah IP termasuk private, loopback, link-local, multicast, reserved, atau documentation."""
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
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
    is_owner: bool = False,
    session_host_id: str = "",
    dj_role_id: str = "",
    action: str = "control",
    target_item_requester_id: Optional[str] = None,
    has_dj_role: bool = False,
) -> Tuple[bool, str]:
    """
    Aturan Host Lock System Per-Server (Admin Server, Role DJ, dan Member):
    - Admin Server (Administrator / Manage Guild) dan pemilik Role DJ dapat mengontrol semua antrean & mode.
    - Session Host dapat mengontrol antrean selama sesinya aktif.
    - Toggle Autoplay & 24/7 Mode dapat diklik oleh Admin, DJ, Session Host, maupun Member ketika tidak terkunci.
    - Member biasa selalu dapat menghapus (remove) item miliknya sendiri.
    """
    if is_admin or is_owner:
        return True, "Diizinkan (Admin Server)."
    if has_dj_role or (dj_role_id and dj_role_id in (user_roles or [])) or ("role-dj" in (user_roles or [])):
        return True, "Diizinkan (Role DJ)."
    if not session_host_id or session_host_id == user_id:
        return True, "Diizinkan (Session Host / Member)."
    if action in ("autoplay", "mode_247"):
        return True, "Diizinkan (Toggle Mode Autoplay / 24/7)."
    if action == "remove_item" and target_item_requester_id and target_item_requester_id == user_id:
        return True, "Diizinkan (Menghapus lagu milik sendiri)."

    return (
        False,
        f"Host Lock aktif: Hanya Session Host (<@{session_host_id}>), Role DJ, atau Admin Server yang dapat melakukan aksi '{action}'.",
    )


def check_host_lock_permission(
    user_id: str,
    user_roles: List[str],
    is_admin: bool,
    is_owner: bool = False,
    session_host_id: str = "",
    dj_role_id: str = "",
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
        raise HTTPException(
            status_code=400,
            detail=f"Parameter {param_name} tidak valid: harus berupa Discord Snowflake ID (15-22 digit).",
        )


def generate_oauth_state(secret_key: str = "") -> str:
    """Menghasilkan token state OAuth2 bertanda tangan HMAC-SHA256 dengan timestamp anti-CSRF."""
    eff_secret = (secret_key or os.getenv("SESSION_SECRET", "athenaa-default-session-secret-key-2026")).encode("utf-8")
    ts = str(int(time.time()))
    nonce = uuid.uuid4().hex
    payload = f"{ts}.{nonce}"
    sig = hmac.new(eff_secret, payload.encode("ascii"), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def verify_oauth_state(state_token: str, secret_key: str = "", max_age_seconds: int = 900) -> bool:
    """Memverifikasi integritas HMAC dan masa berlaku token state OAuth2."""
    if not state_token or "." not in state_token:
        return False
    parts = state_token.strip().split(".")
    if len(parts) != 3:
        return False
    ts_str, nonce, sig = parts
    if not ts_str.isdigit() or not nonce or not sig:
        return False
    now_ts = int(time.time())
    if abs(now_ts - int(ts_str)) > max_age_seconds:
        return False
    eff_secret = (secret_key or os.getenv("SESSION_SECRET", "athenaa-default-session-secret-key-2026")).encode("utf-8")
    expected_sig = hmac.new(eff_secret, f"{ts_str}.{nonce}".encode("ascii"), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig, expected_sig)


SCAM_OR_ABUSE_PATTERNS = re.compile(
    r"(?i)(@everyone|@here|<@&\d+>|discord\.gg/|discord\.gift/|discordapp\.com/invite|"
    r"free\s+nitro|mrbeast|steamcommunnity|dlscord|crypto\s+airdrop|claim\s+your\s+prize|"
    r"t\.me/|bit\.ly/|tinyurl\.com/|porn|bokep|xxx|nsfw|onlyfans|casino|slot\s*gacor|judol)"
)


def sanitize_discord_outbound_text(text: str, max_length: int = 500) -> str:
    """
    Membersihkan teks input pengguna sebelum disimpan atau dikirim ke Discord:
    - Menghapus @everyone, @here, dan mention role (<@&...>)
    - Memblokir tautan invite ilegal, phishing, scam MrBeast/trading/crypto, dan konten NSFW
    """
    if not text:
        return ""
    cleaned = str(text).replace("@everyone", "[everyone]").replace("@here", "[here]")
    cleaned = re.sub(r"<@&\d+>", "[role]", cleaned)
    cleaned = SCAM_OR_ABUSE_PATTERNS.sub("[diblokir-keamanan]", cleaned)
    return cleaned.strip()[:max_length]

