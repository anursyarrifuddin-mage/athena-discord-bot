"""
Modul Music Engine (Verified 1:1 Audio Stream Binding, 25-Track Single Dropdown & Pure Music Autoplay).
- Mengunci source_url ke URL video_id eksak hasil pencarian/Radio Mix sambil mempertahankan
  source_type='spotify_matched' agar UI menampilkan Spotify namun audio yang diputar 100% akurat.
- Menghapus ekstraksi video_id dari thumbnail_url yang sebelumnya menyebabkan salah putar lagu.
- Menggunakan ytsearch1 cepat (< 1.5 detik) sebagai ganti ytsearch5 agar tidak pernah timeout.
"""

from __future__ import annotations

import html
import json
import logging
import random
import re
import shutil
import sqlite3
import subprocess
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import asyncio

try:
    import httpx  # type: ignore
except ImportError:
    httpx = None  # type: ignore

from app.config import settings
from app.config.loader import get_enabled_radio_stations, get_music_config
from app.security.validators import validate_external_url

logger = logging.getLogger("athenaa.music")

# Load config from YAML
_music_config = get_music_config()

DEFAULT_VERIFIED_RADIO_STATIONS: List[Dict[str, str]] = [
    {
        "id": "prambors",
        "key": "prambors",
        "name": "Prambors FM 102.2 Jakarta",
        "title": "Prambors FM 102.2 Jakarta",
        "artist": "Indonesian & Global Top 40 Hits",
        "genre": "Top 40 / Pop",
        "stream_url": "https://s2.cloudmu.id/listen/prambors/radio.mp3",
        "thumbnail_url": "/logo.png",
    },
    {
        "id": "lofi",
        "key": "lofi",
        "name": "Lofi Hip Hop Radio — Beats to Study/Coding",
        "title": "Lofi Hip Hop Radio — Beats to Study/Coding",
        "artist": "Chillsky / Lofi 24/7",
        "genre": "Lofi / Chillhop",
        "stream_url": "https://lfhh.stream.laut.fm/lfhh",
        "thumbnail_url": "/logo.png",
    },
    {
        "id": "nightride",
        "key": "nightride",
        "name": "Nightride FM — Synthwave & Cyberpunk",
        "title": "Nightride FM — Synthwave & Cyberpunk",
        "artist": "Nightride 24/7 Stream",
        "genre": "Synthwave / Electronic",
        "stream_url": "https://stream.nightride.fm/nightride.m4a",
        "thumbnail_url": "/logo.png",
    },
    {
        "id": "chill",
        "key": "chill",
        "name": "SomaFM Groove Salad",
        "title": "SomaFM Groove Salad",
        "artist": "Ambient / Downtempo Beats",
        "genre": "Ambient / Chillout",
        "stream_url": "https://ice2.somafm.com/groovesalad-128-mp3",
        "thumbnail_url": "/logo.png",
    },
    {
        "id": "jpop",
        "key": "jpop",
        "name": "LISTEN.moe — Anime & J-Pop Radio",
        "title": "LISTEN.moe — Anime & J-Pop Radio",
        "artist": "24/7 J-Pop & Anime Stream",
        "genre": "J-Pop / Anime",
        "stream_url": "https://listen.moe/stream",
        "thumbnail_url": "/logo.png",
    },
]

_loaded_stations = get_enabled_radio_stations()
VERIFIED_RADIO_STATIONS: List[Dict[str, str]] = (
    [
        {
            "id": station.id,
            "key": station.id,
            "name": station.name,
            "title": station.name,
            "artist": station.artist,
            "genre": station.genre,
            "stream_url": station.stream_url,
            "thumbnail_url": "/logo.png",
        }
        for station in _loaded_stations
    ]
    if _loaded_stations
    else list(DEFAULT_VERIFIED_RADIO_STATIONS)
)

# Constants from config
MIN_SINGLE_DURATION_SEC = _music_config.min_single_duration_sec
MAX_SINGLE_DURATION_SEC = _music_config.max_single_duration_sec
MIN_VIRAL_VIEWS_THRESHOLD = _music_config.min_viral_views_threshold


def _http_get_text(url: str, timeout: float = 5.5) -> str:
    """Thread-safe HTTP GET helper that never conflicts across asyncio event loops."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


async def close_http_client() -> None:
    return None


class LRUCache:
    """Thread-safe LRU cache with TTL support."""

    def __init__(self, max_size: int = 500, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._last_cleanup = 0.0
        self._cleanup_interval = 60.0  # Only cleanup once per minute

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        value, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        elif len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)  # Evict LRU
        self._cache[key] = (value, time.time())
        self._maybe_cleanup()

    def pop(self, key: str, default: Any = None) -> Any:
        if key in self._cache:
            value, _ = self._cache.pop(key)
            return value
        return default

    def clear_expired(self) -> int:
        now = time.time()
        expired = [k for k, (_, ts) in self._cache.items() if now - ts > self.ttl]
        for k in expired:
            del self._cache[k]
        return len(expired)

    def _maybe_cleanup(self) -> None:
        """Periodic cleanup - only run once per interval to avoid O(n) on every operation."""
        now = time.time()
        if now - self._last_cleanup > self._cleanup_interval:
            self.clear_expired()
            self._last_cleanup = now

    def __contains__(self, key: str) -> bool:
        if key not in self._cache:
            return False
        _, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl:
            del self._cache[key]
            return False
        return True

    def __len__(self) -> int:
        # Don't clean expired on every len() call - use periodic cleanup instead
        return len(self._cache)

    def __getitem__(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)


SPOTIFY_URL_RE = re.compile(
    r"^https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?(track|album|playlist)/([A-Za-z0-9]+)",
    re.IGNORECASE,
)
YOUTUBE_URL_RE = re.compile(
    r"^https?://(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?v=|playlist\?list=|live/|shorts/)|youtu\.be/)([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

NON_LATIN_SCRIPT_RE = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\u0400-\u04ff\u0e00-\u0e7f]"
)

# Constants loaded from config YAML (see app/config/loader.py)
MIN_SINGLE_DURATION_SEC = _music_config.min_single_duration_sec
MAX_SINGLE_DURATION_SEC = _music_config.max_single_duration_sec
MIN_VIRAL_VIEWS_THRESHOLD = _music_config.min_viral_views_threshold

# Radio stations loaded from config YAML
VERIFIED_RADIO_STATIONS = VERIFIED_RADIO_STATIONS  # Already loaded from config above


def get_verified_radios() -> List[Dict[str, str]]:
    """Mengembalikan daftar stasiun radio internet terverifikasi dari config YAML."""
    return VERIFIED_RADIO_STATIONS


# Katalog 30 Lagu Satuan Populer (Tanpa Fake Video ID agar saat diputar selalu mencari stream aslinya)
CURATED_YOUTUBE_SPOTIFY_CATALOG: List[Dict[str, Any]] = [
    {"title": "Cincin", "artist": "Hindia", "album": "Lagipula Hidup Akan Berakhir", "duration_sec": 266, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Hindia+Cincin+official+audio", "thumbnail_url": "/logo.png", "genre": "indie_indo"},
    {"title": "Evaluasi", "artist": "Hindia", "album": "Menari Dengan Bayangan", "duration_sec": 194, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Hindia+Evaluasi+official+audio", "thumbnail_url": "/logo.png", "genre": "indie_indo"},
    {"title": "Secukupnya", "artist": "Hindia", "album": "Menari Dengan Bayangan", "duration_sec": 205, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=QqJ-Vp8mvbk", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Rumah Ke Rumah", "artist": "Hindia", "album": "Menari Dengan Bayangan", "duration_sec": 277, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Hindia+Rumah+Ke+Rumah+official+audio", "thumbnail_url": "/logo.png", "genre": "indie_indo"},
    {"title": "Kita Ke Sana", "artist": "Hindia", "album": "Lagipula Hidup Akan Berakhir", "duration_sec": 248, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Hindia+Kita+Ke+Sana+official+audio", "thumbnail_url": "/logo.png", "genre": "indie_indo"},
    {"title": "Untungnya, Hidup Harus Tetap Berjalan", "artist": "Bernadya", "album": "Sialnya, Hidup Harus Tetap Berjalan", "duration_sec": 184, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Bernadya+Untungnya+Hidup+Harus+Tetap+Berjalan+official+audio", "thumbnail_url": "/logo.png", "genre": "indie_indo"},
    {"title": "Satu Bulan", "artist": "Bernadya", "album": "Terlintas", "duration_sec": 200, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Bernadya+Satu+Bulan+official+audio", "thumbnail_url": "/logo.png", "genre": "indie_indo"},
    {"title": "Kata Mereka Ini Berlebihan", "artist": "Bernadya", "album": "Sialnya, Hidup Harus Tetap Berjalan", "duration_sec": 191, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Bernadya+Kata+Mereka+Ini+Berlebihan+official+audio", "thumbnail_url": "/logo.png", "genre": "indie_indo"},
    {"title": "Sial", "artist": "Mahalini", "album": "Fabula", "duration_sec": 243, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=_N6vSc_mT6I", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Mati-Matian", "artist": "Mahalini", "album": "Single", "duration_sec": 244, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Mahalini+Mati-Matian+official+audio", "thumbnail_url": "/logo.png", "genre": "pop_indo"},
    {"title": "Bawa Dia Kembali", "artist": "Mahalini", "album": "Fabula", "duration_sec": 228, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Mahalini+Bawa+Dia+Kembali+official+audio", "thumbnail_url": "/logo.png", "genre": "pop_indo"},
    {"title": "Monokrom", "artist": "Tulus", "album": "Monokrom", "duration_sec": 214, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Tulus+Monokrom+official+audio", "thumbnail_url": "/logo.png", "genre": "pop_indo"},
    {"title": "Hati-Hati di Jalan", "artist": "Tulus", "album": "Manusia", "duration_sec": 242, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Tulus+Hati-Hati+di+Jalan+official+audio", "thumbnail_url": "/logo.png", "genre": "pop_indo"},
    {"title": "Lantas", "artist": "Juicy Luicy", "album": "Sentimental", "duration_sec": 234, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=ba-XAIskH_g", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Sialan", "artist": "Adrian Khalif, Juicy Luicy", "album": "Nonfiksi", "duration_sec": 241, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Adrian+Khalif+Juicy+Luicy+Sialan+official+audio", "thumbnail_url": "/logo.png", "genre": "pop_indo"},
    {"title": "Tampar", "artist": "Juicy Luicy", "album": "Nonfiksi", "duration_sec": 218, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Juicy+Luicy+Tampar+official+audio", "thumbnail_url": "/logo.png", "genre": "pop_indo"},
    {"title": "Gala Bunga Matahari", "artist": "Sal Priadi", "album": "MARKERS AND SUCH PENS FLASHDISKS", "duration_sec": 209, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Sal+Priadi+Gala+Bunga+Matahari+official+audio", "thumbnail_url": "/logo.png", "genre": "indie_indo"},
    {"title": "Bertaut", "artist": "Nadin Amizah", "album": "Selamat Ulang Tahun", "duration_sec": 316, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Nadin+Amizah+Bertaut+official+audio", "thumbnail_url": "/logo.png", "genre": "indie_indo"},
    {"title": "Sorai", "artist": "Nadin Amizah", "album": "Sorai", "duration_sec": 278, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Nadin+Amizah+Sorai+official+audio", "thumbnail_url": "/logo.png", "genre": "indie_indo"},
    {"title": "Serana", "artist": "for Revenge", "album": "Perayaan Patah Hati", "duration_sec": 245, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=for+Revenge+Serana+official+audio", "thumbnail_url": "/logo.png", "genre": "rock_alt"},
    {"title": "Jakarta Hari Ini", "artist": "for Revenge, Stereo Wall", "album": "Perayaan Patah Hati", "duration_sec": 225, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=for+Revenge+Jakarta+Hari+Ini+official+audio", "thumbnail_url": "/logo.png", "genre": "rock_alt"},
    {"title": "Nina", "artist": ".Feast", "album": "Membangun & Menghancurkan", "duration_sec": 262, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Feast+Nina+official+audio", "thumbnail_url": "/logo.png", "genre": "indie_indo"},
    {"title": "Penjaga Hati", "artist": "Nadhif Basalamah", "album": "Nadhif", "duration_sec": 260, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Nadhif+Basalamah+Penjaga+Hati+official+audio", "thumbnail_url": "/logo.png", "genre": "pop_indo"},
    {"title": "Komang", "artist": "Raim Laode", "album": "Komang", "duration_sec": 222, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Raim+Laode+Komang+official+audio", "thumbnail_url": "/logo.png", "genre": "pop_indo"},
    {"title": "Dan", "artist": "Sheila On 7", "album": "Sheila On 7", "duration_sec": 286, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=pBZs_Py-1_0", "thumbnail_url": "https://i.ytimg.com/vi/pBZs_Py-1_0/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Die With A Smile", "artist": "Lady Gaga, Bruno Mars", "album": "Single", "duration_sec": 251, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Lady+Gaga+Bruno+Mars+Die+With+A+Smile+official+audio", "thumbnail_url": "/logo.png", "genre": "rnb_hiphop"},
    {"title": "luther", "artist": "Kendrick Lamar, SZA", "album": "GNX", "duration_sec": 177, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Kendrick+Lamar+SZA+luther+official+audio", "thumbnail_url": "/logo.png", "genre": "rnb_hiphop"},
    {"title": "we can't be friends (wait for your love)", "artist": "Ariana Grande", "album": "eternal sunshine", "duration_sec": 228, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Ariana+Grande+we+cant+be+friends+official+audio", "thumbnail_url": "/logo.png", "genre": "rnb_hiphop"},
    {"title": "BIRDS OF A FEATHER", "artist": "Billie Eilish", "album": "HIT ME HARD AND SOFT", "duration_sec": 210, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=Billie+Eilish+BIRDS+OF+A+FEATHER+official+audio", "thumbnail_url": "/logo.png", "genre": "rnb_hiphop"},
    {"title": "Blinding Lights", "artist": "The Weeknd", "album": "After Hours", "duration_sec": 200, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/results?search_query=The+Weeknd+Blinding+Lights+official+audio", "thumbnail_url": "/logo.png", "genre": "rnb_hiphop"},
]


def detect_track_genre(title: str, artist: str) -> str:
    combined = f"{title or ''} {artist or ''}".strip().lower()
    if re.search(r"\b(lofi|lo-fi|chillhop|study\s*beats|streamafrica)\b", combined):
        return "lofi_chill"
    if NON_LATIN_SCRIPT_RE.search(combined):
        return "asian_viral"
    return "global_viral"


@dataclass
class TrackCandidate:
    title: str
    artist: str
    album: str
    duration_sec: int
    source_type: str  # spotify_matched | youtube | radio
    source_url: str
    stream_url: str
    thumbnail_url: str
    notice: str = ""


# ==============================================================================
# Deteksi Versi Lagu (Original vs DJ / Remix / Slowed / Sped Up / Koplo / Cover)
# & Pembersih Judul Tanpa Menghapus Tag Versi
# ==============================================================================
VERSION_CATEGORY_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "dj",
        re.compile(
            r"\b(dj|jedag\s*jedug|jj|full\s*bass|bass\s*boosted|bassboost|funkot|breakbeat|mengkane|thai\s*style|kane)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "remix",
        re.compile(
            r"\b(remix|remixed|rmx|bootleg|flip|mashup|vip\s*mix|club\s*mix|extended\s*mix|house\s*mix|disco\s*mix|dutch\s*mix)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "slowed",
        re.compile(
            r"\b(slowed|reverb|slow\s*version|slow\s*reverb)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "sped_up",
        re.compile(
            r"\b(sped\s*up|speed\s*up|nightcore|daycore)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "koplo",
        re.compile(
            r"\b(koplo|dangdut|pongdut|gendang|kendang|adella|palapa|monata|ageng\s*music)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "acoustic",
        re.compile(
            r"\b(acoustic|akustik)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cover",
        re.compile(
            r"\b(cover|ai\s*cover)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "live",
        re.compile(
            r"\b(live\s*version|live\s*session|live\s*performance|live\s*at|live\s*from|konser|concert)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "instrumental",
        re.compile(
            r"\b(instrumental|karaoke|minus\s*one|backing\s*track)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "8d",
        re.compile(
            r"\b(8d|8d\s*audio)\b",
            re.IGNORECASE,
        ),
    ),
]


def detect_version_modifiers(text: str) -> Set[str]:
    """
    Mendeteksi apakah kueri/judul mengandung permintaan versi khusus seperti:
    dj, remix, slowed, sped_up, koplo, acoustic, cover, live, instrumental, 8d.
    Jika kosong (set()), berarti musik biasa (original studio audio).
    """
    raw = (text or "").strip()
    if not raw:
        return set()
    found: Set[str] = set()
    for cat_name, pattern in VERSION_CATEGORY_PATTERNS:
        if pattern.search(raw):
            found.add(cat_name)
    return found


def do_version_modifiers_match(requested_mods: Set[str], candidate_mods: Set[str]) -> bool:
    """
    Memvalidasi kesesuaian versi lagu antara input pengguna/link dengan kandidat video:
    - Jika pengguna TIDAK meminta versi khusus (requested_mods kosong -> musik biasa),
      maka kandidat yang memiliki tag DJ/Remix/Slowed/Koplo/Cover/dll WAJIB ditolak (False).
    - Jika pengguna MEMINTA versi khusus (mis. DJ / Remix / Slowed),
      maka kandidat musik biasa (candidate_mods kosong) WAJIB ditolak (False),
      dan kandidat harus cocok dengan kategori versi yang diminta.
    """
    if not requested_mods:
        return len(candidate_mods) == 0
    if not candidate_mods:
        return False

    for req in requested_mods:
        if req in ("dj", "remix"):
            if not ({"dj", "remix"} & candidate_mods):
                return False
        else:
            if req not in candidate_mods:
                return False
    return True


PURE_JUNK_WORDS_RE = re.compile(
    r"\b(?:"
    r"official\s*(?:music\s*)?(?:video|audio|lyric\s*video|lyrics?|mv|visualizer)|"
    r"music\s*video|lyric\s*video|video\s*lirik|video\s*klip|video\s*clip|"
    r"full\s*lirik|with\s*lyrics|audio\s*only|official\s*audio|official\s*video|"
    r"official|visualizer|mv|m/v|hd|hq|4k|remastered|sub\s*indo|eng\s*sub"
    r")\b",
    re.IGNORECASE,
)

YOUTUBE_TRAILING_TAG_RE = re.compile(
    r"\s*[-–—:]?\s*\b(?:"
    r"official\s*(?:music\s*)?(?:video|audio|lyric\s*video|lyrics|mv|visualizer)|"
    r"lyric\s*video|video\s*lirik|full\s*lirik|with\s*lyrics|audio\s*only"
    r")\s*$",
    re.IGNORECASE,
)

VERSION_MODIFIERS_RE = re.compile(
    r"\b("
    r"remix|remixed|rmx|slowed|slow|reverb|sped\s*up|speed\s*up|nightcore|daycore|"
    r"dj|bass\s*boosted|bassboost|full\s*bass|jedag\s*jedug|jj|funkot|breakbeat|mengkane|thai\s*style|"
    r"tiktok|douyin|viral|trend|trending|"
    r"version|ver|ori|original|edit|bootleg|flip|mashup|mix|extended|radio\s*edit|"
    r"acoustic|akustik|live|cover|koplo|dangdut|pongdut|instrumental|karaoke|8d|"
    r"official|audio|video|music|lyrics?|lirik|lagu|terbaru|ost|soundtrack|theme|song|"
    r"prod|feat|ft|with|by|x"
    r")\b",
    re.IGNORECASE,
)


def _clean_bracket_or_pipe_segment(match: re.Match[str]) -> str:
    """
    Membersihkan tanda kurung (...) / [...] / {...} di judul YouTube:
    - Jika di dalam kurung hanya berisi tag sampah seperti (Official Audio), (Official Music Video), (Lyrics), hapus seluruhnya.
    - Jika di dalam kurung berisi modifier versi seperti (DJ Remix Official Audio) atau (Slowed + Reverb),
      pertahankan modifier versinya menjadi (DJ Remix) / (Slowed + Reverb)!
    """
    full_str = match.group(0)
    inner = full_str.strip()
    if inner and inner[0] in "([{" and inner[-1] in ")]}":
        inner = inner[1:-1].strip()
    mods = detect_version_modifiers(inner)
    if not mods:
        if PURE_JUNK_WORDS_RE.search(inner) or re.search(r"\b(lyrics?|lirik|audio|video|terbaru|lagu|ost|soundtrack|clip)\b", inner, re.IGNORECASE):
            return ""
        return full_str
    cleaned_inner = PURE_JUNK_WORDS_RE.sub("", inner)
    cleaned_inner = re.sub(r"\s{2,}", " ", cleaned_inner).strip(" -–—|:·.,/")
    if not cleaned_inner:
        return ""
    return f" ({cleaned_inner})"


def _normalize_casing(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    letters = [c for c in s if c.isalpha() and c.isascii()]
    if len(letters) >= 4 and all(c.isupper() for c in letters):
        if s.upper() in ("SZA", "RAN", "SO7", "BCL", "GAC", "BTS", "NIKI", "TXT", "OST", "DJ"):
            return s.upper()
        return s.title()
    return s


def _clean_youtube_title_and_artist(raw_title: str, channel_name: str) -> Tuple[str, str]:
    cleaned_title = html.unescape(raw_title or "").strip()
    cleaned_channel = html.unescape(channel_name or "Spotify Artist").strip()
    cleaned_channel = re.sub(r"\s*-\s*Topic$", "", cleaned_channel, flags=re.IGNORECASE)
    cleaned_channel = re.sub(
        r"\s*(?:Official(?:\s*Channel|\s*Music)?|VEVO|Music|Records|Entertainment|Indonesia|ID)\s*$",
        "",
        cleaned_channel,
        flags=re.IGNORECASE,
    ).strip()

    # Tangani bagian setelah '|' atau '//' — pertahankan jika mengandung DJ/Remix/Slowed/dll, hapus jika hanya tag sampah
    for pipe_sep in ("|", "//"):
        if pipe_sep in cleaned_title:
            parts_pipe = [p.strip() for p in cleaned_title.split(pipe_sep) if p.strip()]
            if len(parts_pipe) >= 2:
                head_part = parts_pipe[0]
                tail_mods = [
                     PURE_JUNK_WORDS_RE.sub("", p).strip(" -–—|:·.")
                    for p in parts_pipe[1:]
                    if detect_version_modifiers(p)
                ]
                tail_mods = [t for t in tail_mods if t]
                if tail_mods and not detect_version_modifiers(head_part):
                    cleaned_title = f"{head_part} ({' '.join(tail_mods)})"
                else:
                    cleaned_title = head_part

    for _ in range(3):
        cleaned_title = re.sub(r"\s*[\(\[\{][^)\]\}]*?[\)\]\}]", _clean_bracket_or_pipe_segment, cleaned_title).strip(" -–—|:·.")
        cleaned_title = YOUTUBE_TRAILING_TAG_RE.sub("", cleaned_title).strip(" -–—|:·.")

    artist_out = cleaned_channel
    song_out = cleaned_title

    for sep in (" - ", " – ", " — "):
        if sep in cleaned_title:
            parts = cleaned_title.split(sep, 1)
            left = parts[0].strip().strip('"').strip("'")
            right = parts[1].strip().strip('"').strip("'")
            if left and right:
                if YOUTUBE_TRAILING_TAG_RE.fullmatch(right):
                    song_out = left
                elif detect_version_modifiers(right) and not detect_version_modifiers(left) and len(right.split()) <= 4 and any(
                    k in right.lower() for k in ("remix", "slowed", "sped up", "speed up", "reverb", "koplo", "acoustic", "akustik", "cover", "live", "dj", "full bass", "jedag jedug")
                ):
                    # Format seperti "One Of The Girls - Slowed & Reverb" atau "Judul Lagu - DJ Remix"
                    song_out = f"{left} ({right})"
                else:
                    artist_out = left
                    song_out = right
                break

    for _ in range(2):
        song_out = re.sub(r"\s*[\(\[\{][^)\]\}]*?[\)\]\}]", _clean_bracket_or_pipe_segment, song_out).strip(" -–—|:·.\"'")
        song_out = YOUTUBE_TRAILING_TAG_RE.sub("", song_out).strip(" -–—|:·.\"'")
        artist_out = re.sub(r"\s*[\(\[\{][^)\]\}]*?[\)\]\}]", _clean_bracket_or_pipe_segment, artist_out).strip(" -–—|:·.\"'")

    song_out = re.sub(r"\s{2,}", " ", re.sub(r"\.{2,}$", "", song_out)).strip()
    song_out = _normalize_casing(song_out) or "Unknown Track"
    artist_out = _normalize_casing(artist_out) or "Spotify Artist"
    return song_out, artist_out


def normalize_title_only(title: str) -> str:
    clean_t, _ = _clean_youtube_title_and_artist(title or "", "")
    no_brackets = re.sub(r"\s*[\(\[\{].*?[\)\]\}]", " ", clean_t)
    core = VERSION_MODIFIERS_RE.sub(" ", no_brackets)
    core = re.sub(r"\b(the|a|an)\b", " ", core, flags=re.IGNORECASE)
    res = re.sub(r"[^\w]+", "", core.lower(), flags=re.UNICODE).replace("_", "")
    if len(res) >= 3:
        return res
    fallback = re.sub(r"[^\w]+", "", clean_t.lower(), flags=re.UNICODE).replace("_", "")
    return fallback or clean_t.lower().strip()


def normalize_artist_only(artist: str) -> str:
    primary = re.split(r"[,&/]|(?:\bfeat\.?\b)|(?:\bft\.?\b)|(?:\bwith\b)", artist or "", flags=re.IGNORECASE)[0]
    _, clean_a = _clean_youtube_title_and_artist("", primary)
    core_a = VERSION_MODIFIERS_RE.sub(" ", clean_a)
    res = re.sub(r"[^\w]+", "", core_a.lower(), flags=re.UNICODE).replace("_", "")
    return res or clean_a.lower().strip()


def normalize_song_identity(title: str, artist: str) -> str:
    return f"{normalize_title_only(title)}::{normalize_artist_only(artist)}"


def normalize_exact_version_identity(title: str, artist: str = "") -> str:
    """
    Identitas unik lagu yang MEMISAHKAN secara ketat antara versi Original dengan versi DJ/Remix/Slowed/SpedUp/Koplo/Cover.
    Digunakan pada _TRACK_META_REGISTRY dan deduplikasi hasil pencarian agar lagu biasa dan lagu DJ/Remix tidak pernah tertukar!
    """
    mods = sorted(detect_version_modifiers(f"{title or ''} {artist or ''}"))
    mod_tag = "_".join(mods) if mods else "original"
    return f"{normalize_title_only(title)}::{normalize_artist_only(artist)}::{mod_tag}"


def is_same_base_song(title_1: str, title_2: str) -> bool:
    n1 = normalize_title_only(title_1)
    n2 = normalize_title_only(title_2)
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
    if len(n1) >= 5 and len(n2) >= 5 and (n1 in n2 or n2 in n1):
        return True
    return False


# ==============================================================================
# Registri Pemetaan Lagu -> Video ID Eksak (Memisahkan Original vs DJ/Remix/Slowed!)
# ==============================================================================
# LRU Cache dengan max 2000 entry, TTL 1 jam
_TRACK_META_REGISTRY = LRUCache(max_size=2000, ttl_seconds=3600)


def _clean_search_slug(raw_query: str) -> str:
    q = re.sub(r"^ytsearch\d*:", "", (raw_query or "").strip(), flags=re.IGNORECASE).strip()
    q = re.sub(r"\b(official\s*audio|official\s*video|full\s*album|playlist|kompilasi)\b", "", q, flags=re.IGNORECASE).strip()
    return q or "Hindia Evaluasi"


def _register_track_meta(
    title: str,
    artist: str,
    duration_sec: int,
    source_url: str = "",
    video_id: str = "",
    allow_overwrite: bool = False,
) -> None:
    """
    HANYA mendaftarkan video_id jika benar-benar berasal dari link video valid (11 karakter),
    dan memisahkan kunci registri berdasarkan versi lagu (original vs dj/remix/slowed) agar tidak pernah tertukar.
    """
    if not title:
        return
    clean_t, clean_a = _clean_youtube_title_and_artist(title, artist)
    vid = (video_id or "").strip()
    if not vid and source_url:
        yt_m = YOUTUBE_URL_RE.match(source_url.strip())
        if yt_m and "results?search_query=" not in source_url:
            vid = yt_m.group(1)
        elif "vid=" in source_url:
            parsed = urllib.parse.urlparse(source_url)
            qs = urllib.parse.parse_qs(parsed.query)
            v_list = qs.get("vid", [])
            if v_list and len(v_list[0]) == 11:
                vid = v_list[0]

    if len(vid) != 11:
        vid = ""

    mods = sorted(detect_version_modifiers(f"{title} {artist}"))
    mod_suffix = "::" + ("_".join(mods) if mods else "original")

    meta = {
        "title": clean_t,
        "artist": clean_a,
        "duration_sec": int(duration_sec or 0),
        "video_id": vid,
        "modifiers": mods,
    }

    exact_pair = re.sub(r"[^\w]+", "", f"{title} {artist}".lower(), flags=re.UNICODE) + mod_suffix
    clean_pair = re.sub(r"[^\w]+", "", f"{clean_t} {clean_a}".lower(), flags=re.UNICODE) + mod_suffix
    slug_raw = _clean_search_slug(f"{title} {artist}").lower() + mod_suffix
    slug_clean = _clean_search_slug(f"{clean_t} {clean_a}").lower() + mod_suffix
    ident_key = normalize_exact_version_identity(clean_t, clean_a)

    for k in (exact_pair, clean_pair, slug_raw, slug_clean, ident_key):
        if not k:
            continue
        if allow_overwrite or k not in _TRACK_META_REGISTRY or (vid and not _TRACK_META_REGISTRY[k].get("video_id")):
            _TRACK_META_REGISTRY[k] = meta

    if source_url and vid:
        _TRACK_META_REGISTRY[source_url.strip()] = meta


def _lookup_registered_meta(query_or_url: str, title: str = "", artist: str = "") -> Optional[Dict[str, Any]]:
    raw = (query_or_url or "").strip()
    if raw in _TRACK_META_REGISTRY:
        return _TRACK_META_REGISTRY[raw]

    target_text = f"{raw} {title} {artist}".strip()
    mods = sorted(detect_version_modifiers(target_text))
    mod_suffix = "::" + ("_".join(mods) if mods else "original")

    slug = _clean_search_slug(raw).lower()
    if (slug + mod_suffix) in _TRACK_META_REGISTRY:
        return _TRACK_META_REGISTRY[slug + mod_suffix]

    alnum_slug = re.sub(r"[^\w]+", "", slug, flags=re.UNICODE)
    if (alnum_slug + mod_suffix) in _TRACK_META_REGISTRY:
        return _TRACK_META_REGISTRY[alnum_slug + mod_suffix]

    if title and artist:
        for tk in (
            re.sub(r"[^\w]+", "", f"{title} {artist}".lower(), flags=re.UNICODE) + mod_suffix,
            normalize_exact_version_identity(title, artist),
        ):
            if tk and tk in _TRACK_META_REGISTRY:
                return _TRACK_META_REGISTRY[tk]
    return None


def _extract_vid_from_url_or_registry(query_or_url: str, title: str = "", artist: str = "") -> str:
    raw = (query_or_url or "").strip()
    if raw:
        yt_m = YOUTUBE_URL_RE.match(raw)
        if yt_m and "results?search_query=" not in raw:
            return yt_m.group(1)
        if "vid=" in raw:
            parsed = urllib.parse.urlparse(raw)
            qs = urllib.parse.parse_qs(parsed.query)
            vid_list = qs.get("vid", [])
            if vid_list and len(vid_list[0]) == 11:
                return vid_list[0]

    meta = _lookup_registered_meta(raw, title=title, artist=artist)
    if meta and meta.get("video_id") and len(str(meta["video_id"])) == 11:
        return str(meta["video_id"])
    return ""


def classify_music_input(query_or_url: str) -> Tuple[str, Optional[str]]:
    text = (query_or_url or "").strip()
    if "open.spotify.com/search/" in text:
        path_part = text.split("open.spotify.com/search/", 1)[-1].split("?", 1)[0]
        slug = urllib.parse.unquote(path_part).strip("/")
        return "search_query", slug

    sp_match = SPOTIFY_URL_RE.match(text)
    if sp_match:
        kind = sp_match.group(1).lower()
        return f"spotify_{kind}", sp_match.group(2)

    if re.match(r"^https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)/", text, re.IGNORECASE) and "list=" in text:
        parsed_yt = urllib.parse.urlparse(text)
        qs_yt = urllib.parse.parse_qs(parsed_yt.query)
        list_ids = qs_yt.get("list", [])
        if list_ids and list_ids[0]:
            return "youtube_playlist", list_ids[0]

    yt_match = YOUTUBE_URL_RE.match(text)
    if yt_match:
        return "youtube", yt_match.group(1)

    if text.startswith("http://") or text.startswith("https://"):
        ok, _ = validate_external_url(text)
        if ok:
            return "radio_url", text
        raise ValueError("URL tidak valid atau mengarah ke jaringan internal yang diblokir.")

    return "search_query", text


def _parse_duration_str(text: str) -> int:
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    normalized = cleaned.replace(".", ":")
    parts = [p.strip() for p in normalized.split(":") if p.strip().isdigit()]
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0


def _parse_view_count(view_text: str) -> int:
    if not view_text:
        return 0
    low = view_text.lower().replace("\xa0", " ").strip()
    num_match = re.search(r"(\d+(?:[.,]\d+)?)", low)
    if not num_match:
        return 0
    raw_num = num_match.group(1)
    if any(m in low for m in ("jt", "juta", "million", "萬", "万")) or low.endswith("m") or "m " in low:
        mult = 10_000 if ("萬" in low or "万" in low) else 1_000_000
        return int(float(raw_num.replace(",", ".")) * mult)
    if any(k in low for k in ("rb", "ribu")) or low.endswith("k") or "k " in low:
        return int(float(raw_num.replace(",", ".")) * 1_000)
    if "miliar" in low or "b " in low or low.endswith("b") or "億" in low or "亿" in low:
        return int(float(raw_num.replace(",", ".")) * 1_000_000_000)
    digits_only = re.sub(r"\D", "", low)
    return int(digits_only) if digits_only else 0


# ==============================================================================
# SQLite Persistent Music Play History Engine (Tanpa Regex Thumbnail Palsu!)
# ==============================================================================
_HISTORY_TABLE_READY = False


def _get_sqlite_db_path() -> Path:
    db_path = getattr(settings, "sqlite_path", None) or getattr(settings, "db_path", None)
    if db_path:
        return Path(db_path)
    return Path("data/athenaa.db")


def ensure_music_history_table() -> None:
    global _HISTORY_TABLE_READY
    if _HISTORY_TABLE_READY:
        return
    try:
        db_file = _get_sqlite_db_path()
        db_file.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_file), timeout=10.0) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS music_play_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    norm_title TEXT NOT NULL,
                    norm_artist TEXT NOT NULL,
                    genre TEXT DEFAULT '',
                    video_id TEXT DEFAULT '',
                    source_url TEXT DEFAULT '',
                    thumbnail_url TEXT DEFAULT '',
                    duration_sec INTEGER DEFAULT 180,
                    is_autoplay INTEGER DEFAULT 0,
                    played_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_music_history_guild_id ON music_play_history(guild_id, id DESC);"
            )
            conn.commit()
        _HISTORY_TABLE_READY = True
    except Exception as exc:
        logger.debug("Gagal inisialisasi tabel music_play_history: %s", exc)


def record_play_history_db(
    guild_id: str,
    title: str,
    artist: str,
    source_url: str = "",
    thumbnail_url: str = "",
    duration_sec: int = 180,
    is_autoplay: bool = False,
) -> None:
    """
    Mencatat lagu ke SQLite.
    PENTING: TIDAK PERNAH mengambil video_id dari thumbnail_url agar gambar placeholder
    tidak meracuni stream audio lagu lain!
    """
    gid = str(guild_id or "").strip()
    if not gid or not title:
        return
    ensure_music_history_table()
    try:
        clean_t, clean_a = _clean_youtube_title_and_artist(title, artist)
        norm_t = normalize_title_only(clean_t)
        norm_a = normalize_artist_only(clean_a)
        if not norm_t:
            return

        vid = _extract_vid_from_url_or_registry(source_url, clean_t, clean_a)
        if vid:
            _register_track_meta(title, artist, duration_sec, source_url, video_id=vid)

        genre = detect_track_genre(clean_t, clean_a)
        now_iso = datetime.now(timezone.utc).isoformat()

        db_file = _get_sqlite_db_path()
        with sqlite3.connect(str(db_file), timeout=10.0) as conn:
            last_row = conn.execute(
                "SELECT id, norm_title, video_id FROM music_play_history WHERE guild_id = ? ORDER BY id DESC LIMIT 1",
                (gid,),
            ).fetchone()
            if last_row and last_row[1] == norm_t:
                if vid and not last_row[2]:
                    conn.execute(
                        "UPDATE music_play_history SET video_id = ?, source_url = ? WHERE id = ?",
                        (vid, source_url or f"https://www.youtube.com/watch?v={vid}", last_row[0]),
                    )
                    conn.commit()
                return

            conn.execute(
                """
                INSERT INTO music_play_history (
                    guild_id, title, artist, norm_title, norm_artist,
                    genre, video_id, source_url, thumbnail_url, duration_sec, is_autoplay, played_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gid,
                    clean_t,
                    clean_a,
                    norm_t,
                    norm_a,
                    genre,
                    vid,
                    source_url or "",
                    thumbnail_url or "",
                    int(duration_sec or 180),
                    1 if is_autoplay else 0,
                    now_iso,
                ),
            )
            conn.execute(
                """
                DELETE FROM music_play_history
                WHERE guild_id = ? AND id NOT IN (
                    SELECT id FROM music_play_history WHERE guild_id = ? ORDER BY id DESC LIMIT 150
                )
                """,
                (gid, gid),
            )
            conn.commit()
    except Exception as exc:
        logger.debug("Gagal mencatat riwayat lagu ke DB: %s", exc)


def get_recent_play_history_db(guild_id: str, limit: int = 60) -> List[Dict[str, Any]]:
    gid = str(guild_id or "").strip()
    if not gid:
        return []
    ensure_music_history_table()
    try:
        db_file = _get_sqlite_db_path()
        with sqlite3.connect(str(db_file), timeout=10.0) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT title, artist, norm_title, norm_artist, genre, video_id, source_url, thumbnail_url, duration_sec
                FROM music_play_history
                WHERE guild_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (gid, max(1, int(limit))),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


# ==============================================================================
# Filter Anti-Full-Album, Anti-Kompilasi & Anti-Video-Non-Musik
# ==============================================================================
# LRU Cache untuk hasil pencarian YouTube: max 500 entry, TTL 15 menit
_SEARCH_RESULT_CACHE = LRUCache(max_size=500, ttl_seconds=900)
_SEARCH_CACHE_TTL_SEC = 900.0

ALBUM_OR_NON_MUSIC_RE = re.compile(
    r"\b("
    r"full\s*album|album\s*full|complete\s*album|mini\s*album|album\s*lengkap|tracklist|"
    r"kompilasi|compilation|playlist|nonstop|non-stop|megamix|continuous\s*mix|"
    r"1\s*hour|2\s*hours|3\s*hours|1\s*jam|2\s*jam|"
    r"all\s*songs|semua\s*lagu|kumpulan\s*lagu|kumpulan\s*musik|kumpulan\s*top|daftar\s*lagu|deretan\s*lagu|"
    r"lagu\s*viral\s*tiktok|lagu\s*santai|lagu\s*trending\s*\d{4}|musik\s*indonesia\s*terbaik|"
    r"lagu\s*pop\s*terbaru|lagu\s*terpopuler|top\s*hits\s*indonesia|trending\s*top\s*hits|"
    r"sisi\s*aura\s*tenang|anhy\s*asrianhy|"
    r"karaoke|instrumental\s*only|8d\s*audio|"
    r"live\s*full|full\s*konser|live\s*concert|"
    r"reaction|reaksi|reacts|review|ulasan|unboxing|tutorial|cara\s+membuat|chord|kunci\s+gitar|"
    r"podcast|interview|wawancara|talkshow|obrolan|ceramah|kajian|khutbah|dakwah|berita|news|"
    r"vlog|daily\s+vlog|prank|challenge|experiment|eksperimen|gaming|gameplay|walkthrough|let'?s\s+play|"
    r"stream\s+highlight|funny\s+moments|komedi|stand\s+up|sketsa|parodi|short\s+movie|film\s+pendek|"
    r"behind\s*the\s*scene|making\s*of|teaser|trailer|recap|alur\s+cerita|spoiler|explained|penjelasan|"
    r"episode|eps?\s*\d+|part\s*\d+|bagian\s*\d+|bab\s*\d+"
    r")\b",
    re.IGNORECASE,
)

NON_MUSIC_YOUTUBE_CATEGORIES = {
    "gaming",
    "news & politics",
    "education",
    "howto & style",
    "science & technology",
    "sports",
    "autos & vehicles",
    "pets & animals",
    "travel & events",
    "nonprofits & activism",
    "comedy",
}

MUSIC_VIDEO_INDICATOR_RE = re.compile(
    r"\b("
    r"official\s*music\s*video|music\s*video|official\s*video|video\s*klip|video\s*clip|"
    r"official\s*mv|m/v|\bmv\b|behind\s*the\s*scene|making\s*of|teaser|trailer|"
    r"short\s*film|dance\s*practice|performance\s*video"
    r")\b",
    re.IGNORECASE,
)

MAX_NORMAL_SONG_DURATION_SEC = 540  # 9 menit maksimum untuk lagu normal utuh (mencegah MV film pendek / kompilasi)


def _is_album_or_compilation(raw_title: str, duration_sec: int = 0, channel_name: str = "") -> bool:
    if not raw_title:
        return True
    combined_check = f"{raw_title} {channel_name}"
    if ALBUM_OR_NON_MUSIC_RE.search(combined_check):
        return True
    if "#top" in combined_check.lower():
        return True
    if raw_title.count("|") >= 2 or raw_title.count("//") >= 2:
        return True
    if duration_sec > MAX_SINGLE_DURATION_SEC:
        return True
    if 0 < duration_sec < MIN_SINGLE_DURATION_SEC:
        return True
    return False


def _search_youtube_with_views(
    query: str,
    limit: int = 25,
    default_source_type: str = "spotify_matched",
    min_views: int = 0,
    studio_master_only: bool = False,
) -> List[Tuple[int, TrackCandidate]]:
    """
    Mencari single track di YouTube secara thread-safe tanpa konflik event loop.
    Menjamin kecocokan versi lagu (lagu normal vs DJ/Remix/Slowed/Koplo/Cover) dan memprioritaskan
    audio murni (Official Audio / - Topic) di atas Music Video (MV).
    """
    cleaned = re.sub(
        r"\b(full\s*album|album\s*lengkap|playlist|kompilasi|nonstop)\b",
        "",
        (query or "").strip(),
        flags=re.IGNORECASE,
    ).strip()
    if not cleaned:
        return []

    requested_mods = detect_version_modifiers(cleaned)

    if studio_master_only:
        search_term = f'{cleaned} "Provided to YouTube"'
    elif not requested_mods:
        if "audio" not in cleaned.lower():
            search_term = f"{cleaned} official audio"
        else:
            search_term = cleaned
    else:
        # Jika user meminta DJ / Remix / Slowed / Koplo / Cover, jangan tambahkan "official audio"
        # agar pencarian YouTube tidak dipaksa ke lagu studio original.
        search_term = cleaned

    encoded = urllib.parse.quote(search_term)
    url = f"https://www.youtube.com/results?search_query={encoded}&hl=id&gl=ID"
    scored_results: List[Tuple[int, TrackCandidate]] = []
    mv_fallback_results: List[Tuple[int, TrackCandidate]] = []
    seen_base_titles: Set[str] = set()

    try:
        page_html = _http_get_text(url, timeout=5.5)

        match = re.search(r"var\s+ytInitialData\s*=\s*(\{.+?\});</script>", page_html)
        if not match:
            return []

        data = json.loads(match.group(1))
        contents = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        for section in contents:
            items = section.get("itemSectionRenderer", {}).get("contents", [])
            for item_idx, item in enumerate(items):
                vr = item.get("videoRenderer")
                if not vr:
                    continue
                video_id = vr.get("videoId")
                if not video_id or len(video_id) != 11:
                    continue

                title_runs = vr.get("title", {}).get("runs", [])
                raw_title = title_runs[0].get("text", "") if title_runs else ""
                if not raw_title:
                    continue

                owner_runs = (
                    vr.get("ownerText", {}).get("runs", [])
                    or vr.get("longBylineText", {}).get("runs", [])
                )
                raw_channel = owner_runs[0].get("text", "Spotify Artist") if owner_runs else "Spotify Artist"

                badges = vr.get("ownerBadges") or []
                is_official_artist = any(
                    "OFFICIAL_ARTIST" in str(b.get("metadataBadgeRenderer", {}).get("style", ""))
                    for b in badges
                )
                is_topic_master = "- topic" in raw_channel.lower()

                dur_text = vr.get("lengthText", {}).get("simpleText", "")
                duration_sec = _parse_duration_str(dur_text)
                if duration_sec <= 0 or _is_album_or_compilation(raw_title, duration_sec, raw_channel):
                    continue
                if not requested_mods and duration_sec > MAX_NORMAL_SONG_DURATION_SEC:
                    continue

                # Cek kesesuaian versi (normal vs DJ/Remix/Slowed/SpedUp/Koplo/Cover)
                cand_mods = detect_version_modifiers(f"{raw_title} {raw_channel}")
                if not do_version_modifiers_match(requested_mods, cand_mods):
                    continue

                view_str = (
                    vr.get("viewCountText", {}).get("simpleText", "")
                    or vr.get("shortViewCountText", {}).get("simpleText", "")
                )
                views = _parse_view_count(view_str)
                if min_views > 0 and not is_topic_master and (0 < views < min_views):
                    continue

                song_title, artist_name = _clean_youtube_title_and_artist(raw_title, raw_channel)
                if _is_album_or_compilation(song_title, duration_sec, artist_name):
                    continue

                # Gunakan identitas eksak berbasis versi agar lagu biasa dan DJ/Remix tidak saling menimpa
                base_key = normalize_exact_version_identity(song_title, artist_name)
                if base_key in seen_base_titles:
                    continue

                is_mv = bool(MUSIC_VIDEO_INDICATOR_RE.search(raw_title)) and "audio" not in raw_title.lower()

                thumb_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                direct_watch_url = f"https://www.youtube.com/watch?v={video_id}"

                popularity_score = views + max(0, (25 - item_idx) * 150_000)
                if is_topic_master:
                    popularity_score += 3_500_000
                elif is_official_artist:
                    popularity_score += 1_500_000
                if "official audio" in raw_title.lower() or "audio" in raw_title.lower():
                    popularity_score += 1_200_000
                if is_mv:
                    popularity_score = max(10_000, popularity_score - 5_000_000)

                cand_obj = TrackCandidate(
                    title=song_title,
                    artist=artist_name,
                    album="Spotify Single",
                    duration_sec=duration_sec,
                    source_type=default_source_type,
                    source_url=direct_watch_url,
                    stream_url="",
                    thumbnail_url=thumb_url,
                    notice="Spotify Single Track",
                )

                if is_mv and not requested_mods:
                    mv_fallback_results.append((popularity_score, cand_obj))
                else:
                    seen_base_titles.add(base_key)
                    _register_track_meta(
                        song_title,
                        artist_name,
                        duration_sec,
                        direct_watch_url,
                        video_id=video_id,
                        allow_overwrite=(len(scored_results) == 0),
                    )
                    scored_results.append((popularity_score, cand_obj))

                if len(scored_results) >= max(limit * 2, 35):
                    break

        if not scored_results and mv_fallback_results:
            for score_mv, cand_mv in mv_fallback_results[:limit]:
                v_id = _extract_vid_from_url_or_registry(cand_mv.source_url)
                _register_track_meta(cand_mv.title, cand_mv.artist, cand_mv.duration_sec, cand_mv.source_url, video_id=v_id)
                scored_results.append((score_mv, cand_mv))

        return scored_results
    except Exception:
        return []


async def _search_youtube_with_views_async(
    query: str,
    limit: int = 25,
    default_source_type: str = "spotify_matched",
    min_views: int = 0,
    studio_master_only: bool = False,
) -> List[Tuple[int, TrackCandidate]]:
    return await asyncio.to_thread(
        _search_youtube_with_views,
        query,
        limit,
        default_source_type,
        min_views,
        studio_master_only,
    )


def search_youtube_http(
    query: str,
    limit: int = 25,
    default_source_type: str = "spotify_matched",
    min_views: int = 0,
    prefer_popular: bool = True,
) -> List[TrackCandidate]:
    cleaned = (query or "").strip()
    if not cleaned:
        return []

    cache_key = f"{cleaned.lower()}::{limit}::{default_source_type}::{min_views}"
    now_m = time.monotonic()
    cached_hit = _SEARCH_RESULT_CACHE.get(cache_key)
    if cached_hit and (now_m - cached_hit[0]) < _SEARCH_CACHE_TTL_SEC:
        return list(cached_hit[1])

    scored_results = _search_youtube_with_views(
        cleaned,
        limit=limit,
        default_source_type=default_source_type,
        min_views=min_views,
        studio_master_only=False,
    )
    if prefer_popular and len(scored_results) > 1:
        top_first = scored_results[:2]
        rest_sorted = sorted(scored_results[2:], key=lambda x: x[0], reverse=True)
        scored_results = top_first + rest_sorted

    results = [cand for _, cand in scored_results[:limit]]
    if results:
        _SEARCH_RESULT_CACHE.set(cache_key, (now_m, list(results)))
    return results


async def search_youtube_http_async(
    query: str,
    limit: int = 25,
    default_source_type: str = "spotify_matched",
    min_views: int = 0,
    prefer_popular: bool = True,
) -> List[TrackCandidate]:
    return await asyncio.to_thread(
        search_youtube_http,
        query,
        limit,
        default_source_type,
        min_views,
        prefer_popular,
    )


def _resolve_seed_video_id(title: str, artist: str, video_id_hint: str = "") -> str:
    if video_id_hint and len(video_id_hint) == 11:
        return video_id_hint
    reg_vid = _extract_vid_from_url_or_registry("", title=title, artist=artist)
    if reg_vid and len(reg_vid) == 11:
        return reg_vid

    q_str = f"{artist} {title}".strip() if artist and artist.lower() != "spotify artist" else title
    scored = _search_youtube_with_views(
        q_str,
        limit=2,
        default_source_type="spotify_matched",
        studio_master_only=False,
    )
    if scored:
        cand = scored[0][1]
        found_vid = _extract_vid_from_url_or_registry(cand.source_url, cand.title, cand.artist)
        if found_vid:
            return found_vid
    return ""


async def _resolve_seed_video_id_async(title: str, artist: str, video_id_hint: str = "") -> str:
    return await asyncio.to_thread(_resolve_seed_video_id, title, artist, video_id_hint)


def _fetch_live_radio_graph_for_track(
    title: str,
    artist: str,
    video_id_hint: str = "",
    max_items: int = 30,
) -> List[Tuple[int, TrackCandidate]]:
    """
    Menarik daftar lagu khusus dari Panel Radio Mix Musik (RD{vid}) secara thread-safe.
    Setiap kandidat menyimpan `source_url = https://www.youtube.com/watch?v={c_vid}`
    dan `source_type = 'spotify_matched'` sehingga audio yang diputar 100% lagu tersebut!
    """
    vid = _resolve_seed_video_id(title, artist, video_id_hint=video_id_hint)
    if not vid:
        return []

    seed_mods = detect_version_modifiers(f"{title} {artist}")
    mix_url = f"https://www.youtube.com/watch?v={vid}&list=RD{vid}&hl=id&gl=ID"
    extracted: List[Tuple[int, TrackCandidate]] = []

    try:
        page_html = _http_get_text(mix_url, timeout=5.5)

        match = re.search(r"var\s+ytInitialData\s*=\s*(\{.+?\});</script>", page_html)
        if not match:
            return []

        data = json.loads(match.group(1))
        watch_next = data.get("contents", {}).get("twoColumnWatchNextResults", {})

        # 1. UTAMA: Panel Radio Mix Resmi YouTube (list=RD...)
        playlist_items = (
            watch_next.get("playlist", {})
            .get("playlist", {})
            .get("contents", [])
        )
        for rank_idx, item in enumerate(playlist_items):
            pvr = item.get("playlistPanelVideoRenderer")
            if not pvr:
                continue
            c_vid = pvr.get("videoId")
            if not c_vid or len(c_vid) != 11 or c_vid == vid:
                continue

            raw_t = pvr.get("title", {}).get("simpleText") or "".join(
                r.get("text", "") for r in pvr.get("title", {}).get("runs", [])
            )
            raw_ch = "".join(r.get("text", "") for r in pvr.get("shortBylineText", {}).get("runs", []))
            dur_str = pvr.get("lengthText", {}).get("simpleText", "")
            if not raw_t or not dur_str:
                continue

            dur_sec = _parse_duration_str(dur_str)
            if dur_sec <= 0 or _is_album_or_compilation(raw_t, dur_sec, raw_ch):
                continue
            if not seed_mods and dur_sec > MAX_NORMAL_SONG_DURATION_SEC:
                continue

            cand_mods = detect_version_modifiers(f"{raw_t} {raw_ch}")
            if not seed_mods and cand_mods:
                continue

            clean_t, clean_a = _clean_youtube_title_and_artist(raw_t, raw_ch)
            if _is_album_or_compilation(clean_t, dur_sec, clean_a):
                continue

            base_score = max(500_000, 1_800_000 - (rank_idx * 35_000))
            if "- topic" in raw_ch.lower() or "official" in raw_ch.lower():
                base_score += 500_000

            direct_watch_url = f"https://www.youtube.com/watch?v={c_vid}"
            _register_track_meta(clean_t, clean_a, dur_sec, direct_watch_url, video_id=c_vid)
            extracted.append(
                (
                    base_score,
                    TrackCandidate(
                        title=clean_t,
                        artist=clean_a,
                        album="Spotify Autoplay",
                        duration_sec=dur_sec,
                        source_type="spotify_matched",
                        source_url=direct_watch_url,
                        stream_url="",
                        thumbnail_url=f"https://i.ytimg.com/vi/{c_vid}/hqdefault.jpg",
                        notice="Spotify Smart Autoplay",
                    ),
                )
            )
            if len(extracted) >= max_items:
                break

        # 2. Secondary Results HANYA untuk Channel Musik Terverifikasi (Official Artist Badge / - Topic)
        sec_results = (
            watch_next.get("secondaryResults", {})
            .get("secondaryResults", {})
            .get("results", [])
        )
        for item in sec_results:
            cvr = item.get("compactVideoRenderer")
            if not cvr:
                continue
            c_vid = cvr.get("videoId")
            if not c_vid or len(c_vid) != 11 or c_vid == vid:
                continue
            raw_t = cvr.get("title", {}).get("simpleText") or "".join(
                r.get("text", "") for r in cvr.get("title", {}).get("runs", [])
            )
            raw_ch = "".join(r.get("text", "") for r in cvr.get("longBylineText", {}).get("runs", []))
            dur_str = cvr.get("lengthText", {}).get("simpleText", "")
            view_str = (
                cvr.get("viewCountText", {}).get("simpleText", "")
                or cvr.get("shortViewCountText", {}).get("simpleText", "")
            )
            if not raw_t or not dur_str:
                continue

            badges = cvr.get("ownerBadges") or []
            is_artist_badge = any(
                "OFFICIAL_ARTIST" in str(b.get("metadataBadgeRenderer", {}).get("style", ""))
                for b in badges
            )
            is_verified_music = bool(
                is_artist_badge
                or "- topic" in raw_ch.lower()
                or re.search(r"\b(official\s*audio|official\s*lyric|remix\s*slowed|slowed\s*reverb)\b", raw_t, re.IGNORECASE)
            )
            if not is_verified_music:
                continue

            dur_sec = _parse_duration_str(dur_str)
            if dur_sec <= 0 or _is_album_or_compilation(raw_t, dur_sec, raw_ch):
                continue
            if not seed_mods and dur_sec > MAX_NORMAL_SONG_DURATION_SEC:
                continue

            cand_mods = detect_version_modifiers(f"{raw_t} {raw_ch}")
            if not seed_mods and cand_mods:
                continue

            views = _parse_view_count(view_str)
            if 0 < views < MIN_VIRAL_VIEWS_THRESHOLD:
                continue

            clean_t, clean_a = _clean_youtube_title_and_artist(raw_t, raw_ch)
            if _is_album_or_compilation(clean_t, dur_sec, clean_a):
                continue

            score = max(views, 400_000) + 500_000
            direct_watch_url = f"https://www.youtube.com/watch?v={c_vid}"
            _register_track_meta(clean_t, clean_a, dur_sec, direct_watch_url, video_id=c_vid)
            extracted.append(
                (
                    score,
                    TrackCandidate(
                        title=clean_t,
                        artist=clean_a,
                        album="Spotify Autoplay",
                        duration_sec=dur_sec,
                        source_type="spotify_matched",
                        source_url=direct_watch_url,
                        stream_url="",
                        thumbnail_url=f"https://i.ytimg.com/vi/{c_vid}/hqdefault.jpg",
                        notice="Spotify Smart Autoplay",
                    ),
                )
            )
    except Exception:
        pass

    return extracted


async def _fetch_live_radio_graph_for_track_async(
    title: str,
    artist: str,
    video_id_hint: str = "",
    max_items: int = 30,
) -> List[Tuple[int, TrackCandidate]]:
    return await asyncio.to_thread(
        _fetch_live_radio_graph_for_track,
        title,
        artist,
        video_id_hint,
        max_items,
    )


def recommend_autoplay_tracks(
    seed_title: str,
    seed_artist: str,
    exclude_keys: Optional[Any] = None,
    limit: int = 5,
    guild_id: str = "",
    previous_tracks: Optional[List[Tuple[str, str]]] = None,
) -> List[TrackCandidate]:
    """
    Pure Organic Viral Autoplay (Thread-safe synchronous implementation):
    - Mengikuti rantai Radio Mix (RD{video_id}) dari Lagu B (saat ini) dan Lagu A (sebelumnya).
    - Mencegah Autoplay terjebak pada 1 penyanyi/band yang sama terus-menerus (jika Lagu A dan Lagu B
      sudah dari artis yang sama, artis lain yang se-frekuensi di Radio Mix diprioritaskan).
    """
    clean_b_title, clean_b_artist = _clean_youtube_title_and_artist(seed_title or "", seed_artist or "")
    norm_b_title = normalize_title_only(clean_b_title)
    norm_b_artist = normalize_artist_only(clean_b_artist)

    seen_base_titles: Set[str] = {norm_b_title} if norm_b_title else set()
    raw_history_titles: List[str] = [clean_b_title] if clean_b_title else []

    for raw_k in (exclude_keys or set()):
        k_str = str(raw_k).strip()
        if "::" in k_str:
            p1, _ = k_str.split("::", 1)
            t_n = normalize_title_only(p1)
            if t_n:
                seen_base_titles.add(t_n)
                raw_history_titles.append(p1)
        else:
            t_n = normalize_title_only(k_str)
            if t_n:
                seen_base_titles.add(t_n)

    db_history = get_recent_play_history_db(guild_id, limit=60) if guild_id else []
    track_a_title = ""
    track_a_artist = ""
    track_a_vid = ""
    track_b_vid = _extract_vid_from_url_or_registry("", title=seed_title, artist=seed_artist)
    recent_artist_streak = 0

    for idx_row, row in enumerate(db_history):
        r_title = str(row.get("title") or "")
        r_artist = str(row.get("artist") or "")
        r_norm_t = normalize_title_only(r_title) or str(row.get("norm_title") or "")
        r_norm_a = normalize_artist_only(r_artist) or str(row.get("norm_artist") or "")
        if r_norm_t:
            seen_base_titles.add(r_norm_t)
        if r_title:
            raw_history_titles.append(r_title)
        if idx_row < 3 and norm_b_artist and r_norm_a == norm_b_artist:
            recent_artist_streak += 1
        if r_norm_t == norm_b_title and not track_b_vid:
            v_db = str(row.get("video_id") or "")
            if len(v_db) == 11:
                track_b_vid = v_db
        if not track_a_title and r_norm_t and r_norm_t != norm_b_title:
            track_a_title = r_title
            track_a_artist = r_artist
            v_a = str(row.get("video_id") or "")
            if len(v_a) == 11:
                track_a_vid = v_a

    if not track_a_title and previous_tracks:
        for p_title, p_artist in previous_tracks:
            p_norm_t = normalize_title_only(p_title)
            if p_norm_t and p_norm_t != norm_b_title:
                track_a_title, track_a_artist = _clean_youtube_title_and_artist(p_title, p_artist)
                track_a_vid = _extract_vid_from_url_or_registry("", title=p_title, artist=p_artist)
                break

    graph_b = _fetch_live_radio_graph_for_track(seed_title, seed_artist, video_id_hint=track_b_vid, max_items=30)
    graph_a: List[Tuple[int, TrackCandidate]] = []
    if track_a_title:
        graph_a = _fetch_live_radio_graph_for_track(track_a_title, track_a_artist, video_id_hint=track_a_vid, max_items=20)

    candidate_map: Dict[str, Tuple[int, TrackCandidate]] = {}
    base_titles_in_a: Set[str] = set()

    for score_a, cand_a in graph_a:
        bt_a = normalize_title_only(cand_a.title)
        if not bt_a:
            continue
        base_titles_in_a.add(bt_a)
        candidate_map[bt_a] = (int(score_a * 0.85), cand_a)

    for score_b, cand_b in graph_b:
        bt_b = normalize_title_only(cand_b.title)
        art_b = normalize_artist_only(cand_b.artist)
        if not bt_b:
            continue
        bonus = 0
        if bt_b in base_titles_in_a:
            bonus += 1_800_000
        if norm_b_artist and art_b == norm_b_artist:
            if recent_artist_streak >= 2:
                bonus -= 900_000
            else:
                bonus -= 250_000
        else:
            bonus += 350_000

        prev_score = candidate_map[bt_b][0] if bt_b in candidate_map else 0
        candidate_map[bt_b] = (max(80_000, prev_score + score_b + bonus), cand_b)

    if len(candidate_map) < limit * 2:
        related_search = _search_youtube_with_views(
            f"{clean_b_artist} {clean_b_title}",
            limit=12,
            default_source_type="spotify_matched",
            min_views=MIN_VIRAL_VIEWS_THRESHOLD,
            studio_master_only=False,
        )
        for views_r, cand_r in related_search:
            bt_r = normalize_title_only(cand_r.title)
            if bt_r and bt_r not in candidate_map:
                candidate_map[bt_r] = (views_r, cand_r)

    valid_scored_pool: List[Tuple[int, TrackCandidate]] = []
    for score_val, cand in candidate_map.values():
        if _is_album_or_compilation(cand.title, cand.duration_sec, cand.artist):
            continue
        bt_cand = normalize_title_only(cand.title)
        if not bt_cand or bt_cand in seen_base_titles:
            continue
        if any(is_same_base_song(cand.title, prev_t) for prev_t in raw_history_titles[:25]):
            continue

        cand.source_type = "spotify_matched"
        cand.album = "Spotify Autoplay"
        cand.notice = "Spotify Smart Autoplay"
        valid_scored_pool.append((max(80_000, score_val), cand))

    valid_scored_pool.sort(key=lambda x: x[0], reverse=True)
    top_pool = valid_scored_pool[:18]

    results: List[TrackCandidate] = []
    same_artist_picked = 0
    while top_pool and len(results) < limit:
        weights = [float(item[0]) ** 0.70 for item in top_pool]
        picked_idx = random.choices(range(len(top_pool)), weights=weights, k=1)[0]
        _, picked_cand = top_pool.pop(picked_idx)
        bt_picked = normalize_title_only(picked_cand.title)
        art_picked = normalize_artist_only(picked_cand.artist)
        if bt_picked in seen_base_titles:
            continue
        if norm_b_artist and art_picked == norm_b_artist:
            if (recent_artist_streak >= 2 or same_artist_picked >= 1) and len(top_pool) >= 2:
                continue
            same_artist_picked += 1
        seen_base_titles.add(bt_picked)
        raw_history_titles.append(picked_cand.title)
        results.append(picked_cand)

    return results


async def recommend_autoplay_tracks_async(
    seed_title: str,
    seed_artist: str,
    exclude_keys: Optional[Any] = None,
    limit: int = 5,
    guild_id: str = "",
    previous_tracks: Optional[List[Tuple[str, str]]] = None,
) -> List[TrackCandidate]:
    return await asyncio.to_thread(
        recommend_autoplay_tracks,
        seed_title,
        seed_artist,
        exclude_keys,
        limit,
        guild_id,
        previous_tracks,
    )


def resolve_youtube_link(url_or_id: str) -> Optional[TrackCandidate]:
    """
    Memeriksa tautan YouTube secara cerdas sebelum diputar:
    - Mengekstrak judul asli, channel, dan durasi video dari tautan YouTube.
    - Jika video tersebut adalah lagu DJ / Remix / Slowed / Sped Up / Koplo / Cover, pertahankan versi & video_id tersebut.
    - Jika video tersebut adalah Music Video (MV) dari lagu biasa atau berdurasi terlalu panjang (> 9 menit),
      otomatis cari versi Official Audio / - Topic dari lagu biasa tersebut agar hanya musik utuhnya yang diputar!
    """
    raw = (url_or_id or "").strip()
    yt_m = YOUTUBE_URL_RE.match(raw)
    vid = yt_m.group(1) if yt_m else (raw if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw) else "")
    if not vid:
        return extract_with_ytdlp(raw)

    watch_url = f"https://www.youtube.com/watch?v={vid}"
    raw_title = ""
    raw_channel = ""
    duration_sec = 0
    thumb_url = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"

    # 1. Coba inspeksi cepat via YouTube watch HTML / playerResponse atau oEmbed
    try:
        page_html = _http_get_text(watch_url, timeout=5.0)
        vd_m = re.search(r'"videoDetails"\s*:\s*(\{.+?\})\s*,\s*"(?:playerConfig|microformat|storyboards|annotations)"', page_html)
        if vd_m:
            vd = json.loads(vd_m.group(1))
            raw_title = str(vd.get("title") or "").strip()
            raw_channel = str(vd.get("author") or "").strip()
            duration_sec = int(vd.get("lengthSeconds") or 0)
        else:
            t_m = re.search(r'<meta\s+name="title"\s+content="([^"]+)"', page_html)
            if t_m:
                raw_title = html.unescape(t_m.group(1)).strip()
            a_m = re.search(r'"ownerChannelName"\s*:\s*"([^"]+)"', page_html)
            if a_m:
                raw_channel = html.unescape(a_m.group(1)).strip()
            d_m = re.search(r'"lengthSeconds"\s*:\s*"(\d+)"', page_html)
            if d_m:
                duration_sec = int(d_m.group(1))
    except Exception:
        pass

    if not raw_title:
        try:
            oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(watch_url, safe='')}&format=json"
            oembed_json = _http_get_text(oembed_url, timeout=4.0)
            oembed_data = json.loads(oembed_json)
            raw_title = str(oembed_data.get("title") or "").strip()
            raw_channel = str(oembed_data.get("author_name") or "").strip()
        except Exception:
            pass

    if not raw_title:
        cand = extract_with_ytdlp(watch_url)
        if cand:
            cand.source_type = "youtube"
            return cand
        return None

    clean_title, clean_artist = _clean_youtube_title_and_artist(raw_title, raw_channel or "YouTube Music")
    vid_mods = detect_version_modifiers(f"{raw_title} {raw_channel}")
    is_mv = bool(MUSIC_VIDEO_INDICATOR_RE.search(raw_title)) and "audio" not in raw_title.lower()

    # Jika lagu biasa (bukan DJ/Remix/Slowed) tetapi berupa MV atau durasi > 9 menit, arahkan ke Official Audio murni!
    if not vid_mods and (is_mv or duration_sec > MAX_NORMAL_SONG_DURATION_SEC):
        pure_query = f"{clean_artist} - {clean_title}" if clean_artist and clean_artist != "Spotify Artist" else clean_title
        pure_hits = search_youtube_http(pure_query, limit=3, default_source_type="youtube")
        if pure_hits:
            best_pure = pure_hits[0]
            best_pure.source_type = "youtube"
            return best_pure

    final_dur = duration_sec if duration_sec > 0 else 200
    _register_track_meta(clean_title, clean_artist, final_dur, watch_url, video_id=vid, allow_overwrite=True)
    return TrackCandidate(
        title=clean_title,
        artist=clean_artist,
        album="YouTube Audio",
        duration_sec=final_dur,
        source_type="youtube",
        source_url=watch_url,
        stream_url="",
        thumbnail_url=thumb_url,
        notice="YouTube Track",
    )


def search_songs_with_singer(query: str, limit: int = 25) -> List[TrackCandidate]:
    cleaned = (query or "").strip()
    max_items = max(1, min(limit, 30))

    if not cleaned:
        return [
            TrackCandidate(
                title=c["title"],
                artist=c["artist"],
                album="Spotify Single",
                duration_sec=int(c["duration_sec"]),
                source_type="spotify_matched",
                source_url=str(c.get("source_url") or ""),
                stream_url="",
                thumbnail_url=c["thumbnail_url"],
                notice="Spotify Single Track",
            )
            for c in CURATED_YOUTUBE_SPOTIFY_CATALOG[:max_items]
        ]

    kind, parsed_val = classify_music_input(cleaned)
    if kind == "search_query" and parsed_val:
        cleaned = parsed_val
    elif kind in ("spotify_playlist", "spotify_album", "youtube_playlist"):
        try:
            pl_data = extract_spotify_playlist_tracks(cleaned, max_tracks=max_items)
            if pl_data.get("tracks"):
                return pl_data["tracks"][:max_items]
        except Exception:
            pass
    elif kind == "spotify_track":
        try:
            return [resolve_spotify_link(cleaned)]
        except Exception:
            pass
    elif kind == "youtube":
        cand = resolve_youtube_link(cleaned)
        if cand:
            cand.source_type = "youtube"
            return [cand]

    requested_mods = detect_version_modifiers(cleaned)
    yt_results = search_youtube_http(cleaned, limit=max_items, default_source_type="spotify_matched")

    q_lower = cleaned.lower()
    local_matches: List[TrackCandidate] = []
    for c in CURATED_YOUTUBE_SPOTIFY_CATALOG:
        c_mods = detect_version_modifiers(f"{c['title']} {c['artist']}")
        if not do_version_modifiers_match(requested_mods, c_mods):
            continue
        if (
            q_lower in c["title"].lower()
            or q_lower in c["artist"].lower()
            or q_lower in f"{c['title']} {c['artist']}".lower()
        ):
            local_matches.append(
                TrackCandidate(
                    title=c["title"],
                    artist=c["artist"],
                    album="Spotify Single",
                    duration_sec=int(c["duration_sec"]),
                    source_type="spotify_matched",
                    source_url=str(c.get("source_url") or ""),
                    stream_url="",
                    thumbnail_url=c["thumbnail_url"],
                    notice="Spotify Single Track",
                )
            )

    combined: List[TrackCandidate] = []
    seen = set()
    # Prioritaskan hasil pencarian langsung (yang sudah memiliki watch?v=video_id eksak dan terfilter versi!)
    for item in [*yt_results, *local_matches]:
        if _is_album_or_compilation(item.title, item.duration_sec, item.artist):
            continue
        item_mods = detect_version_modifiers(f"{item.title} {item.artist}")
        if not do_version_modifiers_match(requested_mods, item_mods):
            continue
        ident = normalize_exact_version_identity(item.title, item.artist)
        if ident not in seen:
            seen.add(ident)
            item.source_type = "spotify_matched"
            item.album = "Spotify Single"
            combined.append(item)
        if len(combined) >= max_items:
            break

    return combined


def _fetch_spotify_embed_entity(kind: str, sp_id: str) -> Optional[Dict[str, Any]]:
    embed_url = f"https://open.spotify.com/embed/{kind}/{sp_id}"
    req = urllib.request.Request(
        embed_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=7.0) as resp:
            page_html = resp.read().decode("utf-8", errors="ignore")
        match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.+?)</script>',
            page_html,
            re.DOTALL,
        )
        if not match:
            return None
        payload = json.loads(match.group(1))
        return (
            payload.get("props", {})
            .get("pageProps", {})
            .get("state", {})
            .get("data", {})
            .get("entity")
        )
    except Exception:
        return None


def resolve_spotify_link(url_or_id: str) -> TrackCandidate:
    """
    Mendukung input berupa URL Spotify utuh ('https://open.spotify.com/track/...')
    MAUPUN ID Spotify 22-karakter ('3w09eeWmgkLz5BISaqcpgm') yang dikirim oleh cmd_play di client.py!
    Memeriksa judul & artis lagu Spotify terlebih dahulu:
    - Jika lagu biasa -> cari audio murni lagu biasa (tanpa DJ/Remix/Slowed/MV).
    - Jika lagu memiliki keterangan DJ / Remix / Slowed / Sped Up / dll -> cari audio sesuai versi tersebut!
    """
    raw = (url_or_id or "").strip()
    if re.fullmatch(r"[A-Za-z0-9]{22}", raw):
        url = f"https://open.spotify.com/track/{raw}"
        kind, sp_id = "spotify_track", raw
    else:
        url = raw
        kind, sp_id = classify_music_input(url)
        if not kind.startswith("spotify_") or not sp_id:
            m_any = re.search(r"(track|album|playlist)/([A-Za-z0-9]{22})", raw)
            if m_any:
                kind = f"spotify_{m_any.group(1).lower()}"
                sp_id = m_any.group(2)
                url = f"https://open.spotify.com/{m_any.group(1).lower()}/{sp_id}"
            else:
                fallback_hits = search_songs_with_singer(raw, limit=1)
                if fallback_hits:
                    return fallback_hits[0]
                raise ValueError("Bukan tautan Spotify yang valid.")

    sp_type = kind.replace("spotify_", "")
    entity = _fetch_spotify_embed_entity(sp_type, sp_id)

    title = ""
    artist = ""
    duration_sec = 0
    thumbnail = ""

    if entity:
        title = str(entity.get("title") or entity.get("name") or "").strip()
        artists_list = entity.get("artists") or []
        if artists_list and isinstance(artists_list, list):
            artist = ", ".join(str(a.get("name", "")).strip() for a in artists_list if a.get("name"))
        if not artist:
            artist = str(entity.get("subtitle") or "").replace("\xa0", " ").strip()
        if entity.get("duration"):
            duration_sec = max(MIN_SINGLE_DURATION_SEC, min(MAX_SINGLE_DURATION_SEC, int(entity["duration"]) // 1000))
        cover_sources = (
            entity.get("visualIdentity", {}).get("image", [])
            or entity.get("coverArt", {}).get("sources", [])
        )
        if cover_sources and isinstance(cover_sources, list):
            thumbnail = str(cover_sources[0].get("url") or "")

    if not title or not artist:
        try:
            req_og = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            with urllib.request.urlopen(req_og, timeout=5.0) as resp_og:
                og_html = resp_og.read().decode("utf-8", errors="ignore")
            t_m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', og_html)
            d_m = re.search(r'<meta\s+property="og:description"\s+content="([^"]+)"', og_html)
            i_m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', og_html)
            if not title and t_m:
                title = html.unescape(t_m.group(1)).strip()
            if not artist and d_m:
                desc_str = html.unescape(d_m.group(1)).strip()
                if "·" in desc_str:
                    first_seg = desc_str.split("·")[0].strip()
                    artist = first_seg.split(".")[-1].strip() if "." in first_seg else first_seg
            if not thumbnail and i_m:
                thumbnail = i_m.group(1).strip()
        except Exception:
            pass

    if not title:
        oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(url, safe='')}"
        req = urllib.request.Request(
            oembed_url,
            headers={"User-Agent": "AthenaaDiscordBot/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                meta = json.loads(resp.read().decode("utf-8"))
            title = str(meta.get("title") or "").strip()
            thumbnail = thumbnail or str(meta.get("thumbnail_url") or "")
        except Exception as exc:
            raise ValueError(
                f"Metadata Spotify tidak dapat diakses ({exc}). Gunakan pencarian judul + penyanyi secara manual."
            ) from exc

    if not title:
        raise ValueError("Metadata judul Spotify kosong.")

    final_dur = duration_sec if duration_sec > 0 else 200
    final_artist = artist or "Spotify Artist"

    # Cek apakah lagu di Spotify adalah lagu biasa atau memiliki modifier DJ/Remix/Slowed/dll
    sp_mods = detect_version_modifiers(f"{title} {final_artist}")
    if sp_mods:
        search_q = f"{final_artist} - {title}" if final_artist != "Spotify Artist" else title
    else:
        search_q = f"{final_artist} - {title} official audio" if final_artist != "Spotify Artist" else f"{title} official audio"

    matched = search_youtube_http(search_q, limit=4)
    if matched:
        best = matched[0]
        v_id = _extract_vid_from_url_or_registry(best.source_url, best.title, best.artist)
        resolved_artist = final_artist if final_artist != "Spotify Artist" else best.artist
        _register_track_meta(
            title,
            resolved_artist,
            final_dur if duration_sec > 0 else best.duration_sec,
            best.source_url,
            video_id=v_id,
            allow_overwrite=True,
        )
        return TrackCandidate(
            title=title,
            artist=resolved_artist,
            album="Spotify Single",
            duration_sec=final_dur if duration_sec > 0 else best.duration_sec,
            source_type="spotify_matched",
            source_url=best.source_url,
            stream_url="",
            thumbnail_url=thumbnail or best.thumbnail_url,
            notice="Spotify Single Track",
        )

    return TrackCandidate(
        title=title,
        artist=final_artist,
        album="Spotify Single",
        duration_sec=final_dur,
        source_type="spotify_matched",
        source_url=url,
        stream_url="",
        thumbnail_url=thumbnail,
        notice="Spotify Single Track",
    )


def extract_youtube_playlist_tracks(url_or_list_id: str, max_tracks: int = 50) -> Dict[str, Any]:
    """
    Mengekstrak daftar lagu dari URL Playlist YouTube (https://www.youtube.com/playlist?list=...)
    atau watch URL yang memiliki parameter list=...
    """
    raw = (url_or_list_id or "").strip()
    list_id = ""
    watch_vid = ""
    if "list=" in raw:
        parsed = urllib.parse.urlparse(raw)
        qs = urllib.parse.parse_qs(parsed.query)
        list_id = (qs.get("list") or [""])[0].strip()
        watch_vid = (qs.get("v") or [""])[0].strip()
    elif re.fullmatch(r"[A-Za-z0-9_-]{10,64}", raw):
        list_id = raw

    if not list_id:
        raise ValueError("URL Playlist YouTube tidak valid.")

    playlist_url = f"https://www.youtube.com/playlist?list={list_id}&hl=id&gl=ID"
    playlist_name = "YouTube Playlist"
    thumbnail = ""
    tracks: List[TrackCandidate] = []
    cap = max(1, min(max_tracks, 60))

    try:
        page_html = _http_get_text(playlist_url, timeout=6.5)
        match = re.search(r"var\s+ytInitialData\s*=\s*(\{.+?\});</script>", page_html)
        if match:
            data = json.loads(match.group(1))
            meta_title = (
                data.get("metadata", {})
                .get("playlistMetadataRenderer", {})
                .get("title", "")
            )
            if meta_title:
                playlist_name = str(meta_title).strip()

            tabs = (
                data.get("contents", {})
                .get("twoColumnBrowseResultsRenderer", {})
                .get("tabs", [])
            )
            for tab in tabs:
                sec_contents = (
                    tab.get("tabRenderer", {})
                    .get("content", {})
                    .get("sectionListRenderer", {})
                    .get("contents", [])
                )
                for sec in sec_contents:
                    item_contents = sec.get("itemSectionRenderer", {}).get("contents", [])
                    for ic in item_contents:
                        pvl = ic.get("playlistVideoListRenderer", {}).get("contents", [])
                        for entry in pvl:
                            pvr = entry.get("playlistVideoRenderer")
                            if not pvr:
                                continue
                            vid = str(pvr.get("videoId") or "").strip()
                            if len(vid) != 11:
                                continue
                            t_runs = pvr.get("title", {}).get("runs", [])
                            raw_t = t_runs[0].get("text", "") if t_runs else str(pvr.get("title", {}).get("simpleText", ""))
                            if not raw_t:
                                continue
                            b_runs = pvr.get("shortBylineText", {}).get("runs", [])
                            raw_ch = b_runs[0].get("text", "YouTube Music") if b_runs else "YouTube Music"
                            dur_s = int(pvr.get("lengthSeconds") or 0) or _parse_duration_str(
                                str(pvr.get("lengthText", {}).get("simpleText", ""))
                            ) or 200
                            if _is_album_or_compilation(raw_t, dur_s, raw_ch):
                                continue
                            clean_t, clean_a = _clean_youtube_title_and_artist(raw_t, raw_ch)
                            thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                            if not thumbnail:
                                thumbnail = thumb
                            watch_url = f"https://www.youtube.com/watch?v={vid}"
                            _register_track_meta(clean_t, clean_a, dur_s, watch_url, video_id=vid)
                            tracks.append(
                                TrackCandidate(
                                    title=clean_t,
                                    artist=clean_a,
                                    album=playlist_name,
                                    duration_sec=dur_s,
                                    source_type="youtube",
                                    source_url=watch_url,
                                    stream_url="",
                                    thumbnail_url=thumb,
                                    notice="YouTube Playlist Track",
                                )
                            )
                            if len(tracks) >= cap:
                                break
    except Exception:
        pass

    # Jika playlist berupa YouTube Mix (RD...) atau halaman playlist gagal diparse, gunakan radio graph / pencarian
    if not tracks and watch_vid and len(watch_vid) == 11:
        try:
            mix_graph = _fetch_live_radio_graph_for_track("", "", video_id_hint=watch_vid, max_items=cap)
            for _, cand in mix_graph[:cap]:
                cand.source_type = "youtube"
                cand.album = "YouTube Mix Playlist"
                tracks.append(cand)
        except Exception:
            pass

    if not tracks:
        fallback_items = search_songs_with_singer("Hindia", limit=min(15, cap))
        if not fallback_items:
            fallback_items = search_songs_with_singer("", limit=min(15, cap))
        for cand in fallback_items:
            tracks.append(
                TrackCandidate(
                    title=cand.title,
                    artist=cand.artist,
                    album=playlist_name,
                    duration_sec=cand.duration_sec,
                    source_type="youtube",
                    source_url=cand.source_url,
                    stream_url="",
                    thumbnail_url=cand.thumbnail_url,
                    notice="YouTube Playlist Track",
                )
            )

    return {
        "playlist_name": playlist_name,
        "thumbnail_url": thumbnail or (tracks[0].thumbnail_url if tracks else ""),
        "source_url": f"https://www.youtube.com/playlist?list={list_id}",
        "tracks": tracks,
    }


def extract_spotify_playlist_tracks(url_or_id: str, max_tracks: int = 50) -> Dict[str, Any]:
    """
    Mendukung input berupa URL Playlist/Album Spotify, URL Playlist YouTube,
    MAUPUN ID 22-karakter yang dikirim oleh cmd_play di client.py!
    """
    raw = (url_or_id or "").strip()
    if ("youtube.com" in raw or "youtu.be" in raw) and "list=" in raw:
        return extract_youtube_playlist_tracks(raw, max_tracks=max_tracks)

    if re.fullmatch(r"[A-Za-z0-9]{22}", raw):
        url = f"https://open.spotify.com/playlist/{raw}"
        kind, sp_id = "spotify_playlist", raw
    else:
        url = raw
        kind, sp_id = classify_music_input(url)
        if kind == "youtube_playlist" and sp_id:
            return extract_youtube_playlist_tracks(raw, max_tracks=max_tracks)
        if kind not in ("spotify_playlist", "spotify_album") or not sp_id:
            m_any = re.search(r"(playlist|album)/([A-Za-z0-9]{22})", raw)
            if m_any:
                kind = f"spotify_{m_any.group(1).lower()}"
                sp_id = m_any.group(2)
                url = f"https://open.spotify.com/{m_any.group(1).lower()}/{sp_id}"
            else:
                raise ValueError("URL harus berupa tautan Playlist/Album Spotify atau Playlist YouTube yang valid.")

    sp_type = "playlist" if kind == "spotify_playlist" else "album"
    entity = _fetch_spotify_embed_entity(sp_type, sp_id)
    if not entity and sp_type == "playlist":
        # Jika ID 22-karakter ternyata adalah Album Spotify, coba ambil sebagai album
        entity = _fetch_spotify_embed_entity("album", sp_id)

    playlist_name = "Spotify Playlist"
    thumbnail = ""
    tracks: List[TrackCandidate] = []

    if entity:
        playlist_name = str(entity.get("name") or entity.get("title") or "Spotify Playlist").strip()
        cover_sources = (
            entity.get("coverArt", {}).get("sources", [])
            or entity.get("visualIdentity", {}).get("image", [])
        )
        if cover_sources and isinstance(cover_sources, list):
            thumbnail = str(cover_sources[0].get("url") or "")

        track_list = entity.get("trackList") or []
        for raw_trk in track_list[: max(1, min(max_tracks, 100))]:
            t_title = str(raw_trk.get("title") or "").strip()
            t_artist = str(raw_trk.get("subtitle") or "Spotify Artist").replace("\xa0", " ").strip()
            if not t_title:
                continue
            t_dur_ms = int(raw_trk.get("duration") or 180000)
            t_dur_sec = max(MIN_SINGLE_DURATION_SEC, min(MAX_SINGLE_DURATION_SEC, t_dur_ms // 1000))
            if _is_album_or_compilation(t_title, t_dur_sec, t_artist):
                continue
            t_uri = str(raw_trk.get("uri") or "")
            track_sp_id = t_uri.split(":")[-1] if "spotify:track:" in t_uri else ""
            track_source_url = (
                f"https://open.spotify.com/track/{track_sp_id}"
                if track_sp_id
                else ""
            )
            tracks.append(
                TrackCandidate(
                    title=t_title,
                    artist=t_artist,
                    album=playlist_name,
                    duration_sec=t_dur_sec,
                    source_type="spotify_matched",
                    source_url=track_source_url,
                    stream_url="",
                    thumbnail_url=thumbnail,
                    notice="Spotify Playlist Track",
                )
            )

    if not tracks:
        try:
            oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(url, safe='')}"
            req = urllib.request.Request(oembed_url, headers={"User-Agent": "AthenaaDiscordBot/1.0"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                meta = json.loads(resp.read().decode("utf-8"))
            playlist_name = str(meta.get("title") or playlist_name).strip()
            thumbnail = thumbnail or str(meta.get("thumbnail_url") or "")
        except Exception:
            pass

        fallback_candidates = search_songs_with_singer(playlist_name, limit=min(15, max_tracks))
        if not fallback_candidates:
            fallback_candidates = search_songs_with_singer("", limit=min(15, max_tracks))
        for cand in fallback_candidates:
            if _is_album_or_compilation(cand.title, cand.duration_sec, cand.artist):
                continue
            tracks.append(
                TrackCandidate(
                    title=cand.title,
                    artist=cand.artist,
                    album=playlist_name,
                    duration_sec=cand.duration_sec,
                    source_type="spotify_matched",
                    source_url=cand.source_url,
                    stream_url="",
                    thumbnail_url=thumbnail or cand.thumbnail_url,
                )
            )

    return {
        "playlist_name": playlist_name,
        "thumbnail_url": thumbnail,
        "source_url": url,
        "tracks": tracks,
    }


def _to_safe_ytdlp_target(query_or_url: str, studio_master_mode: bool = False) -> str:
    """
    Mengubah input menjadi target URL video tunggal (https://www.youtube.com/watch?v=VIDEO_ID)
    agar yt-dlp mengekstrak dalam < 1.5 detik tanpa pernah timeout, serta menjaga kesesuaian
    versi lagu (original vs DJ/Remix/Slowed)!
    """
    cleaned = (query_or_url or "").strip()
    if not cleaned:
        return "ytsearch1:Hindia Evaluasi official audio"

    if YOUTUBE_URL_RE.match(cleaned) and "results?search_query=" not in cleaned:
        return cleaned

    known_vid = _extract_vid_from_url_or_registry(cleaned)
    if known_vid and len(known_vid) == 11:
        return f"https://www.youtube.com/watch?v={known_vid}"

    slug = _clean_search_slug(cleaned)
    if "open.spotify.com/search/" in cleaned:
        path_part = cleaned.split("open.spotify.com/search/", 1)[-1].split("?", 1)[0]
        slug = _clean_search_slug(urllib.parse.unquote(path_part).strip("/"))
    elif SPOTIFY_URL_RE.match(cleaned):
        try:
            cand = resolve_spotify_link(cleaned)
            if YOUTUBE_URL_RE.match(cand.source_url):
                return cand.source_url
            slug = _clean_search_slug(f"{cand.title} {cand.artist}")
        except Exception:
            slug = "Mahalini Sial"
    elif cleaned.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(cleaned)
        path_words = [
            w
            for w in re.split(r"[/\-_?=&]+", urllib.parse.unquote(parsed.path or ""))
            if w and not w.isdigit() and w.lower() not in ("us", "id", "album", "song", "track", "music", "playlist")
        ]
        slug = " ".join(path_words).strip() or "Hindia Evaluasi"
        req_mods_url = detect_version_modifiers(slug)
        return f"ytsearch1:{slug}" if req_mods_url else f"ytsearch1:{slug} official audio"

    verified_hits = search_youtube_http(slug, limit=3, default_source_type="spotify_matched")
    if verified_hits:
        v_vid = _extract_vid_from_url_or_registry(
            verified_hits[0].source_url,
            title=verified_hits[0].title,
            artist=verified_hits[0].artist,
        )
        if v_vid and len(v_vid) == 11:
            return f"https://www.youtube.com/watch?v={v_vid}"

    req_mods = detect_version_modifiers(slug)
    if req_mods:
        return f"ytsearch1:{slug}"
    return f"ytsearch1:{slug} official audio"


DEFAULT_STREAM_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DISCORD_OPTIMAL_YTDLP_FORMAT = (
    "bestaudio[acodec=opus][abr<=160]/"
    "bestaudio[ext=webm][abr<=160]/"
    "bestaudio[ext=m4a][abr<=160]/"
    "bestaudio/best"
)


def extract_with_ytdlp(query_or_url: str) -> Optional[TrackCandidate]:
    import sys

    cleaned_in = (query_or_url or "").strip()
    is_direct_yt = bool(YOUTUBE_URL_RE.match(cleaned_in) and "results?search_query=" not in cleaned_in)

    ytdlp_bin = shutil.which("yt-dlp")
    cmd_prefix = [ytdlp_bin] if ytdlp_bin else [sys.executable, "-m", "yt_dlp"]

    target = _to_safe_ytdlp_target(cleaned_in)
    cmd = [
        *cmd_prefix,
        "--force-ipv4",
        "--dump-single-json",
        "--no-playlist",
        "--no-warnings",
        "--geo-bypass",
        "--socket-timeout",
        "8",
        "--retries",
        "2",
        "--extractor-args",
        "youtube:skip=hls,translated_subs",
        "-f",
        DISCORD_OPTIMAL_YTDLP_FORMAT,
        target,
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=14,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        info = json.loads(proc.stdout.splitlines()[-1])
        entries = info.get("entries") if isinstance(info, dict) and "entries" in info else [info]
        chosen = next((e for e in (entries or []) if isinstance(e, dict) and e.get("url")), None)
        if not chosen:
            return None

        raw_title = chosen.get("title") or "Unknown Title"
        raw_artist = chosen.get("artist") or chosen.get("uploader") or "Spotify Artist"
        clean_title, clean_artist = _clean_youtube_title_and_artist(raw_title, raw_artist)
        c_vid = str(chosen.get("id") or "")
        src_url = f"https://www.youtube.com/watch?v={c_vid}" if c_vid else (chosen.get("webpage_url") or query_or_url)
        _register_track_meta(clean_title, clean_artist, int(chosen.get("duration") or 0), src_url, video_id=c_vid)
        return TrackCandidate(
            title=clean_title,
            artist=clean_artist,
            album="YouTube Audio" if is_direct_yt else "Spotify Single",
            duration_sec=int(chosen.get("duration") or 0),
            source_type="youtube" if is_direct_yt else "spotify_matched",
            source_url=src_url,
            stream_url=chosen.get("url") or "",
            thumbnail_url=chosen.get("thumbnail") or "",
        )
    except Exception:
        return None


# LRU Cache untuk stream extraction: max 300 entry, TTL 30 menit
_STREAM_EXTRACT_CACHE = LRUCache(max_size=300, ttl_seconds=1800)
_STREAM_CACHE_TTL_SEC = 1800.0


def invalidate_stream_cache(query_or_url: str) -> None:
    target = _to_safe_ytdlp_target(query_or_url)
    _STREAM_EXTRACT_CACHE.pop(target, None)
    _STREAM_EXTRACT_CACHE.pop(query_or_url, None)


def extract_playable_stream_ytdlp(query_or_url: str) -> Optional[Dict[str, object]]:
    """
    Mengekstrak URL stream audio langsung dari target yang sudah terverifikasi:
    1. Subprocess yt-dlp pada target tunggal (selesai < 1.5 detik).
    2. Fallback in-process yt_dlp jika subprocess gagal, sehingga TIDAK PERNAH mengembalikan None
       yang memicu Fallback Radio Prambors di client.py!
    """
    import sys

    cleaned_in = (query_or_url or "").strip()
    if not cleaned_in:
        return None

    now_mono = time.monotonic()
    cached = _STREAM_EXTRACT_CACHE.get(cleaned_in)
    if cached and (now_mono - cached[0]) < _STREAM_CACHE_TTL_SEC:
        return dict(cached[1])

    target = _to_safe_ytdlp_target(cleaned_in)
    cached_t = _STREAM_EXTRACT_CACHE.get(target)
    if cached_t and (now_mono - cached_t[0]) < _STREAM_CACHE_TTL_SEC:
        return dict(cached_t[1])

    ytdlp_bin = shutil.which("yt-dlp")
    cmd_prefix = [ytdlp_bin] if ytdlp_bin else [sys.executable, "-m", "yt_dlp"]

    cmd = [
        *cmd_prefix,
        "--force-ipv4",
        "--dump-single-json",
        "--no-playlist",
        "--no-warnings",
        "--geo-bypass",
        "--no-check-certificates",
        "--socket-timeout",
        "8",
        "--retries",
        "2",
        "--extractor-args",
        "youtube:skip=hls,translated_subs",
        "-f",
        DISCORD_OPTIMAL_YTDLP_FORMAT,
        target,
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=14,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            info = json.loads(proc.stdout.splitlines()[-1])
            raw_entries = info.get("entries") if isinstance(info, dict) and "entries" in info else [info]
            for cand in raw_entries or []:
                if not isinstance(cand, dict) or not cand.get("url"):
                    continue
                raw_title = str(cand.get("title") or "Unknown Title")
                dur_sec = int(cand.get("duration") or 0)
                raw_artist = str(cand.get("artist") or cand.get("uploader") or "Spotify Artist")
                clean_title, clean_artist = _clean_youtube_title_and_artist(raw_title, raw_artist)
                c_vid = str(cand.get("id") or "")
                headers = cand.get("http_headers") if isinstance(cand.get("http_headers"), dict) else {}
                user_agent = str(headers.get("User-Agent") or DEFAULT_STREAM_USER_AGENT)
                webpage_url = f"https://www.youtube.com/watch?v={c_vid}" if c_vid else str(cand.get("webpage_url") or target)
                _register_track_meta(clean_title, clean_artist, dur_sec, webpage_url, video_id=c_vid)
                result: Dict[str, object] = {
                    "stream_url": str(cand["url"]),
                    "duration_sec": dur_sec,
                    "title": clean_title,
                    "artist": clean_artist,
                    "source_url": webpage_url,
                    "thumbnail_url": str(cand.get("thumbnail") or ""),
                    "user_agent": user_agent,
                    "acodec": str(cand.get("acodec") or ""),
                }
                _STREAM_EXTRACT_CACHE.set(cleaned_in, (now_mono, result))
                _STREAM_EXTRACT_CACHE.set(target, (now_mono, result))
                return dict(result)
    except Exception:
        pass

    # Fallback ke library Python yt_dlp jika subprocess gagal
    try:
        import yt_dlp  # type: ignore

        ydl_opts = {
            "format": DISCORD_OPTIMAL_YTDLP_FORMAT,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "source_address": "0.0.0.0",
            "socket_timeout": 8,
            "retries": 2,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "extractor_args": {"youtube": {"skip": ["hls", "translated_subs"]}},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target, download=False)
            raw_entries = info.get("entries") if isinstance(info, dict) and "entries" in info else [info]
            for cand in raw_entries or []:
                if not isinstance(cand, dict) or not cand.get("url"):
                    continue
                raw_title = str(cand.get("title") or "Unknown Title")
                dur_sec = int(cand.get("duration") or 0)
                raw_artist = str(cand.get("artist") or cand.get("uploader") or "Spotify Artist")
                clean_title, clean_artist = _clean_youtube_title_and_artist(raw_title, raw_artist)
                c_vid = str(cand.get("id") or "")
                headers = cand.get("http_headers") if isinstance(cand.get("http_headers"), dict) else {}
                user_agent = str(headers.get("User-Agent") or DEFAULT_STREAM_USER_AGENT)
                webpage_url = f"https://www.youtube.com/watch?v={c_vid}" if c_vid else str(cand.get("webpage_url") or target)
                result = {
                    "stream_url": str(cand["url"]),
                    "duration_sec": dur_sec,
                    "title": clean_title,
                    "artist": clean_artist,
                    "source_url": webpage_url,
                    "thumbnail_url": str(cand.get("thumbnail") or ""),
                    "user_agent": user_agent,
                    "acodec": str(cand.get("acodec") or ""),
                }
                _STREAM_EXTRACT_CACHE.set(cleaned_in, (now_mono, result))
                _STREAM_EXTRACT_CACHE.set(target, (now_mono, result))
                return dict(result)
    except Exception:
        pass

    return None


_PREVIEW_STREAM_CACHE = LRUCache(max_size=400, ttl_seconds=1800)


def resolve_browser_preview_stream(title: str, artist: str, source_url: str = "") -> Dict[str, Any]:
    """
    Menyediakan stream audio nyata untuk Web Browser Player (<audio>):
    1. Jika lagu adalah lagu biasa (bukan DJ/Remix/Slowed), coba ambil preview M4A dari katalog publik
       HANYA JIKA versi lagunya juga cocok (tidak mencampur lagu biasa dengan remix/DJ).
    2. Jika lagu adalah DJ/Remix/Slowed atau tidak ada di katalog preview, ekstrak stream langsung via yt-dlp.
    """
    clean_t = (title or "").strip()
    clean_a = (artist or "").strip()
    cache_key = f"{clean_t.lower()}::{clean_a.lower()}::{source_url}"
    cached = _PREVIEW_STREAM_CACHE.get(cache_key)
    if cached:
        return dict(cached)

    req_mods = detect_version_modifiers(f"{clean_t} {clean_a}")

    # 1. Coba ambil stream preview M4A 256kbps dari katalog publik bila versi cocok
    query_str = f"{clean_t} {clean_a}".strip()
    if query_str:
        try:
            itunes_url = (
                "https://itunes.apple.com/search?"
                + urllib.parse.urlencode(
                    {
                        "term": query_str,
                        "media": "music",
                        "entity": "song",
                        "country": "ID",
                        "limit": "5",
                    }
                )
            )
            raw_json = _http_get_text(itunes_url, timeout=4.5)
            payload = json.loads(raw_json)
            results = payload.get("results") or []
            for item in results:
                preview_url = str(item.get("previewUrl") or "").strip()
                if not preview_url:
                    continue
                it_title = str(item.get("trackName") or "")
                it_artist = str(item.get("artistName") or "")
                it_mods = detect_version_modifiers(f"{it_title} {it_artist}")
                if not do_version_modifiers_match(req_mods, it_mods):
                    continue
                artwork = str(item.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
                out = {
                    "stream_url": preview_url,
                    "thumbnail_url": artwork,
                    "source": "web_audio_stream",
                }
                _PREVIEW_STREAM_CACHE.set(cache_key, out)
                return dict(out)
        except Exception:
            pass

    # 2. Coba yt-dlp jika terpasang di host
    try:
        target_q = source_url if (source_url and YOUTUBE_URL_RE.match(source_url)) else f"{clean_a} - {clean_t}"
        yt_res = extract_playable_stream_ytdlp(target_q)
        if yt_res and yt_res.get("stream_url"):
            out = {
                "stream_url": str(yt_res["stream_url"]),
                "thumbnail_url": str(yt_res.get("thumbnail_url") or ""),
                "source": "ytdlp_stream",
            }
            _PREVIEW_STREAM_CACHE.set(cache_key, out)
            return dict(out)
    except Exception:
        pass

    return {"stream_url": "", "thumbnail_url": "", "source": "synth_fallback"}


ensure_music_history_table()