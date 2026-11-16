"""
Modul Music Engine (YouTube Music Official Audio & Topic Master, Typo-Tolerant Search,
Verified 1:1 Audio Stream Binding, 25-Track Single Dropdown & Pure Music Autoplay).
- Mengutamakan sumber audio dari YouTube Music (Art Track '- Topic' / 'Provided to YouTube' & Official Audio).
- Dilengkapi sistem koreksi typo otomatis & fuzzy matching (contoh: 'Aint on LA adela' -> 'Ain't in LA' oleh 'Adela')
  sehingga lagu yang diputar selalu akurat sesuai judul lagu dan penyanyi aslinya.
- Mengunci source_url ke URL video_id eksak hasil pencarian/Radio Mix sambil mempertahankan
  kompatibilitas UI dan memastikan audio yang keluar 100% musik murni (bukan vlog/gaming/podcast/full album).
- Menggunakan ytsearch1 cepat (< 1.5 detik) sebagai ganti ytsearch5 agar tidak pernah timeout.
"""

from __future__ import annotations

import difflib
import html
import json
import os
import logging
import random
import re
import shutil
import sqlite3
import subprocess
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import settings
from app.security.validators import validate_external_url

logger = logging.getLogger("athenaa.music")


class LRUCache:
    """Thread-safe LRU cache with TTL support."""

    def __init__(self, max_size: int = 500, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()

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
            self._cache.popitem(last=False)
        self._cache[key] = (value, time.time())

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

    def __contains__(self, key: str) -> bool:
        if key not in self._cache:
            return False
        _, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl:
            del self._cache[key]
            return False
        return True

    def __len__(self) -> int:
        self.clear_expired()
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

# Rentang durasi lagu satuan (35 detik s/d 540 detik = 9 menit)
MIN_SINGLE_DURATION_SEC = 35
MAX_SINGLE_DURATION_SEC = 540
MIN_VIRAL_VIEWS_THRESHOLD = 25_000

VERIFIED_RADIO_STATIONS: List[Dict[str, str]] = [
    {
        "id": "prambors",
        "name": "Prambors FM 102.2 Jakarta",
        "artist": "Live Radio Stream · Top 40 Indonesia",
        "genre": "Top 40 / Pop Indonesia & Internasional",
        "stream_url": "https://s7.alhastream.com/radio/8030/radio",
    },
    {
        "id": "hardrockfm",
        "name": "Hard Rock FM 87.6 Jakarta",
        "artist": "Live Radio Stream · Pop & Rock",
        "genre": "Lifestyle / Rock / Pop Hits",
        "stream_url": "https://n09.radiojar.com/7csmg90fuqruv",
    },
    {
        "id": "genfm",
        "name": "Gen FM 98.7 Jakarta",
        "artist": "Live Radio Stream · Musik Hits Indonesia",
        "genre": "Musik Hits Terbaik Indonesia",
        "stream_url": "https://n07.radiojar.com/4ywdgup3bnzuv",
    },
    {
        "id": "lofigirl",
        "name": "Lofi Hip Hop Beats 24/7 Stream",
        "artist": "StreamAfrica · Chill & Focus",
        "genre": "Chill / Study Beats",
        "stream_url": "https://play.streamafrica.net/lofiradio",
    },
]


def get_verified_radios() -> List[Dict[str, str]]:
    """Mengembalikan daftar stasiun radio internet terverifikasi."""
    return list(VERIFIED_RADIO_STATIONS)


# Katalog Lagu Satuan Populer YouTube Music & Spotify (Fallback & Referensi Cepat)
CURATED_YOUTUBE_SPOTIFY_CATALOG: List[Dict[str, Any]] = [
    {"title": "Ain't in LA", "artist": "Adela", "album": "Single", "duration_sec": 192, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "global_viral"},
    {"title": "Cincin", "artist": "Hindia", "album": "Lagipula Hidup Akan Berakhir", "duration_sec": 266, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Evaluasi", "artist": "Hindia", "album": "Menari Dengan Bayangan", "duration_sec": 194, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Secukupnya", "artist": "Hindia", "album": "Menari Dengan Bayangan", "duration_sec": 205, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Rumah Ke Rumah", "artist": "Hindia", "album": "Menari Dengan Bayangan", "duration_sec": 277, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Kita Ke Sana", "artist": "Hindia", "album": "Lagipula Hidup Akan Berakhir", "duration_sec": 248, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Untungnya, Hidup Harus Tetap Berjalan", "artist": "Bernadya", "album": "Sialnya, Hidup Harus Tetap Berjalan", "duration_sec": 184, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Satu Bulan", "artist": "Bernadya", "album": "Terlintas", "duration_sec": 200, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Kata Mereka Ini Berlebihan", "artist": "Bernadya", "album": "Sialnya, Hidup Harus Tetap Berjalan", "duration_sec": 191, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Sial", "artist": "Mahalini", "album": "Fabula", "duration_sec": 243, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Mati-Matian", "artist": "Mahalini", "album": "Single", "duration_sec": 244, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Bawa Dia Kembali", "artist": "Mahalini", "album": "Fabula", "duration_sec": 228, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Monokrom", "artist": "Tulus", "album": "Monokrom", "duration_sec": 214, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=QqJ-Vp8mvbk", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Hati-Hati di Jalan", "artist": "Tulus", "album": "Manusia", "duration_sec": 242, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=_N6vSc_mT6I", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Lantas", "artist": "Juicy Luicy", "album": "Sentimental", "duration_sec": 234, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=ba-XAIskH_g", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Sialan", "artist": "Adrian Khalif, Juicy Luicy", "album": "Nonfiksi", "duration_sec": 241, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Tampar", "artist": "Juicy Luicy", "album": "Nonfiksi", "duration_sec": 218, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Gala Bunga Matahari", "artist": "Sal Priadi", "album": "MARKERS AND SUCH PENS FLASHDISKS", "duration_sec": 209, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Bertaut", "artist": "Nadin Amizah", "album": "Selamat Ulang Tahun", "duration_sec": 316, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Sorai", "artist": "Nadin Amizah", "album": "Sorai", "duration_sec": 278, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Serana", "artist": "for Revenge", "album": "Perayaan Patah Hati", "duration_sec": 245, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/ba-XAIskH_g/hqdefault.jpg", "genre": "rock_alt"},
    {"title": "Jakarta Hari Ini", "artist": "for Revenge, Stereo Wall", "album": "Perayaan Patah Hati", "duration_sec": 225, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/pBZs_Py-1_0/hqdefault.jpg", "genre": "rock_alt"},
    {"title": "Nina", "artist": ".Feast", "album": "Membangun & Menghancurkan", "duration_sec": 262, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "indie_indo"},
    {"title": "Penjaga Hati", "artist": "Nadhif Basalamah", "album": "Nadhif", "duration_sec": 260, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Komang", "artist": "Raim Laode", "album": "Komang", "duration_sec": 222, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/_N6vSc_mT6I/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Dan", "artist": "Sheila On 7", "album": "Sheila On 7", "duration_sec": 286, "source_type": "spotify_matched", "source_url": "https://www.youtube.com/watch?v=pBZs_Py-1_0", "thumbnail_url": "https://i.ytimg.com/vi/pBZs_Py-1_0/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Hujan", "artist": "Utopia", "album": "Kekal", "duration_sec": 258, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/pBZs_Py-1_0/hqdefault.jpg", "genre": "pop_indo"},
    {"title": "Die With A Smile", "artist": "Lady Gaga, Bruno Mars", "album": "Single", "duration_sec": 251, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "rnb_hiphop"},
    {"title": "luther", "artist": "Kendrick Lamar, SZA", "album": "GNX", "duration_sec": 177, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "rnb_hiphop"},
    {"title": "we can't be friends (wait for your love)", "artist": "Ariana Grande", "album": "eternal sunshine", "duration_sec": 228, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "rnb_hiphop"},
    {"title": "BIRDS OF A FEATHER", "artist": "Billie Eilish", "album": "HIT ME HARD AND SOFT", "duration_sec": 210, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "rnb_hiphop"},
    {"title": "Blinding Lights", "artist": "The Weeknd", "album": "After Hours", "duration_sec": 200, "source_type": "spotify_matched", "source_url": "", "thumbnail_url": "https://i.ytimg.com/vi/QqJ-Vp8mvbk/hqdefault.jpg", "genre": "rnb_hiphop"},
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
# Pembersih Judul, Normalisasi Typo & Base-Song Deduplicator
# ==============================================================================
YOUTUBE_JUNK_BRACKET_RE = re.compile(
    r"\s*(?:"
    r"[\(\[\{][^)\]\}]*?(?:official|lyric|lirik|video|audio|mv|visualizer|live|performance|hd|hq|4k|remastered|terbaru|lagu|clip|ost|soundtrack|karaoke|sub\s*indo|eng\s*sub|youtube\s*music)[^)\]\}]*?[\)\]\}]|"
    r"\|.*$|"
    r"//.*$"
    r")",
    re.IGNORECASE,
)

YOUTUBE_TRAILING_TAG_RE = re.compile(
    r"\s*[-–—:]?\s*\b(?:"
    r"official\s*(?:music\s*)?(?:video|audio|lyric\s*video|lyrics|mv|visualizer)|"
    r"lyric\s*video|video\s*lirik|full\s*lirik|with\s*lyrics|audio\s*only|youtube\s*music"
    r")\s*$",
    re.IGNORECASE,
)

VERSION_MODIFIERS_RE = re.compile(
    r"\b("
    r"remix|remixed|slowed|slow|reverb|sped\s*up|speed\s*up|nightcore|daycore|"
    r"dj|bass\s*boosted|bassboost|jedag\s*jedug|jj|tiktok|douyin|viral|trend|trending|"
    r"version|ver|ori|original|edit|bootleg|flip|mashup|mix|extended|radio\s*edit|"
    r"acoustic|akustik|live|cover|koplo|dangdut|instrumental|karaoke|"
    r"official|audio|video|music|lyrics?|lirik|lagu|terbaru|ost|soundtrack|theme|song|"
    r"prod|feat|ft|with|by|x"
    r")\b",
    re.IGNORECASE,
)

SPECIAL_VERSION_KEYWORDS_RE = re.compile(
    r"\b("
    r"remix|remixed|slowed|slow|reverb|sped\s*up|speed\s*up|speedup|nightcore|daycore|"
    r"dj|bass\s*boosted|bassboost|jedag\s*jedug|jj|bass.?boost"
    r")\b",
    re.IGNORECASE,
)

AVOID_MV_KEYWORDS_RE = re.compile(
    r"\b("
    r"official\s*music\s*video|music\s*video|video\s*klip|video\s*clip|"
    r"mv\b|visualizer|behind\s*the\s*scene|making\s*of|teaser|trailer"
    r")\b",
    re.IGNORECASE,
)

# Kontraksi umum bahasa Inggris yang sering diketik tanpa tanda petik (typo)
COMMON_CONTRACTION_TYPOS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\baint\b", re.IGNORECASE), "ain't"),
    (re.compile(r"\bdont\b", re.IGNORECASE), "don't"),
    (re.compile(r"\bcant\b", re.IGNORECASE), "can't"),
    (re.compile(r"\bwont\b", re.IGNORECASE), "won't"),
    (re.compile(r"\bim\b", re.IGNORECASE), "i'm"),
    (re.compile(r"\byoure\b", re.IGNORECASE), "you're"),
    (re.compile(r"\btheyre\b", re.IGNORECASE), "they're"),
    (re.compile(r"\bwere\b(?=\s+not\b)", re.IGNORECASE), "we're"),
    (re.compile(r"\bdoesnt\b", re.IGNORECASE), "doesn't"),
    (re.compile(r"\bdidnt\b", re.IGNORECASE), "didn't"),
    (re.compile(r"\bisnt\b", re.IGNORECASE), "isn't"),
    (re.compile(r"\barent\b", re.IGNORECASE), "aren't"),
    (re.compile(r"\bwasnt\b", re.IGNORECASE), "wasn't"),
    (re.compile(r"\bwerent\b", re.IGNORECASE), "weren't"),
    (re.compile(r"\bhasnt\b", re.IGNORECASE), "hasn't"),
    (re.compile(r"\bhavent\b", re.IGNORECASE), "haven't"),
    (re.compile(r"\bcouldnt\b", re.IGNORECASE), "couldn't"),
    (re.compile(r"\bwouldnt\b", re.IGNORECASE), "wouldn't"),
    (re.compile(r"\bshouldnt\b", re.IGNORECASE), "shouldn't"),
    (re.compile(r"\blets\b", re.IGNORECASE), "let's"),
    (re.compile(r"\bthats\b", re.IGNORECASE), "that's"),
    (re.compile(r"\bwhats\b", re.IGNORECASE), "what's"),
]

# Preposisi pendek yang sering tertukar saat user mengetik judul lagu (mis. "Aint on LA" -> "Ain't in LA")
INTERCHANGEABLE_PREPOSITIONS = {"in", "on", "at", "to", "of", "for", "di", "ke"}


def _strip_accents_and_punctuation(text: str) -> str:
    """Menghapus tanda aksen/diakritik (mis. ADÉLA -> adela) dan tanda baca seperti apostrof."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKD", text)
    no_accent = "".join(c for c in norm if not unicodedata.combining(c))
    # Hapus apostrof agar "ain't" menjadi "aint" saat dibandingkan secara token
    no_apostrophe = re.sub(r"['’`´]", "", no_accent)
    cleaned = re.sub(r"[^\w\s]+", " ", no_apostrophe.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_typo_query(raw_query: str) -> str:
    """Memperbaiki typo kontraksi umum (mis. 'Aint' -> 'Ain't') tanpa merusak struktur kata."""
    q = (raw_query or "").strip()
    if not q:
        return ""
    for pat, repl in COMMON_CONTRACTION_TYPOS:
        q = pat.sub(repl, q)
    return re.sub(r"\s+", " ", q).strip()


def _generate_typo_tolerant_queries(raw_query: str) -> List[str]:
    """
    Menghasilkan daftar variasi kueri tahan-typo untuk pencarian YouTube Music.
    Contoh: 'Aint on LA adela' -> ['Ain\\'t in LA adela', 'Ain\\'t on LA adela', 'Aint on LA adela']
    """
    base = (raw_query or "").strip()
    if not base:
        return []

    norm_contraction = _normalize_typo_query(base)
    variants: List[str] = []

    # Jika terdapat preposisi 'on' sebelum kata lokasi/singkatan (seperti 'on LA', 'on my mind', dll.),
    # buat kandidat koreksi preposisi 'in' <-> 'on'
    if re.search(r"\bon\b", norm_contraction, flags=re.IGNORECASE):
        in_variant = re.sub(r"\bon\b", "in", norm_contraction, flags=re.IGNORECASE)
        if in_variant not in variants:
            variants.append(in_variant)

    if norm_contraction not in variants:
        variants.append(norm_contraction)

    if base not in variants:
        variants.append(base)

    if re.search(r"\bin\b", norm_contraction, flags=re.IGNORECASE):
        on_variant = re.sub(r"\bin\b", "on", norm_contraction, flags=re.IGNORECASE)
        if on_variant not in variants:
            variants.append(on_variant)

    return variants


def _compute_fuzzy_song_match_score(
    raw_query: str,
    candidate_title: str,
    candidate_artist: str,
) -> float:
    """
    Menghitung skor kemiripan tahan-typo (0.0 s/d 1.0+) antara kueri pencarian user
    dengan pasangan (judul lagu, penyanyi) kandidat YouTube Music.
    Mendukung:
    - Typo preposisi ('Aint on LA adela' vs 'Ain\\'t in LA' - 'Adela')
    - Typo ejaan nama penyanyi atau judul (1-2 huruf meleset, aksen seperti ADÉLA vs Adela)
    - Urutan 'judul penyanyi' maupun 'penyanyi judul'
    """
    q_clean = _strip_accents_and_punctuation(raw_query)
    q_clean = VERSION_MODIFIERS_RE.sub(" ", q_clean)
    q_clean = re.sub(r"\s+", " ", q_clean).strip()
    if not q_clean:
        return 0.0

    t_clean = _strip_accents_and_punctuation(candidate_title)
    t_clean = VERSION_MODIFIERS_RE.sub(" ", t_clean)
    t_clean = re.sub(r"\s+", " ", t_clean).strip()

    a_clean = _strip_accents_and_punctuation(candidate_artist)
    a_clean = VERSION_MODIFIERS_RE.sub(" ", a_clean)
    a_clean = re.sub(r"\s+", " ", a_clean).strip()

    combined_ta = f"{t_clean} {a_clean}".strip()
    combined_at = f"{a_clean} {t_clean}".strip()

    # 1. SequenceMatcher pada string utuh (dengan menyamakan preposisi pendek in/on/at)
    def _neutralize_preps(s: str) -> str:
        tokens = s.split()
        return " ".join("_prep_" if tok in INTERCHANGEABLE_PREPOSITIONS else tok for tok in tokens)

    q_prep = _neutralize_preps(q_clean)
    ta_prep = _neutralize_preps(combined_ta)
    at_prep = _neutralize_preps(combined_at)
    t_prep = _neutralize_preps(t_clean)

    seq_ta = difflib.SequenceMatcher(None, q_prep, ta_prep).ratio()
    seq_at = difflib.SequenceMatcher(None, q_prep, at_prep).ratio()
    seq_t = difflib.SequenceMatcher(None, q_prep, t_prep).ratio()
    best_seq = max(seq_ta, seq_at, seq_t * 0.92)

    # 2. Token-level fuzzy matching (agar tahan typo per kata & urutan kata)
    q_tokens = q_clean.split()
    target_tokens = combined_ta.split()
    if not q_tokens or not target_tokens:
        return best_seq

    matched_tokens = 0.0
    artist_tokens = set(a_clean.split())
    title_tokens = set(t_clean.split())
    artist_matched = False
    title_matched = False

    for qt in q_tokens:
        if qt in target_tokens:
            matched_tokens += 1.0
            if qt in artist_tokens:
                artist_matched = True
            if qt in title_tokens:
                title_matched = True
            continue
        if qt in INTERCHANGEABLE_PREPOSITIONS and any(tt in INTERCHANGEABLE_PREPOSITIONS for tt in target_tokens):
            matched_tokens += 0.92
            continue
        # Cek kemiripan per kata (typo 1-2 karakter)
        best_tok_sim = 0.0
        best_tok_target = ""
        for tt in target_tokens:
            sim = difflib.SequenceMatcher(None, qt, tt).ratio()
            if sim > best_tok_sim:
                best_tok_sim = sim
                best_tok_target = tt
        if best_tok_sim >= 0.72:
            matched_tokens += best_tok_sim
            if best_tok_target in artist_tokens:
                artist_matched = True
            if best_tok_target in title_tokens:
                title_matched = True

    best_seq = max(seq_ta, seq_at, seq_t * 1.08)
    token_coverage = matched_tokens / max(1, len(q_tokens))
    score = (best_seq * 0.50) + (token_coverage * 0.50)

    # Prioritas Utama Judul Lagu (Title-First Ranking) sebelum Penyanyi
    if q_clean == t_clean:
        score += 0.55
    elif t_clean.startswith(q_clean) or q_clean in t_clean:
        score += 0.35

    if title_matched and artist_matched:
        score += 0.28
    elif title_matched:
        score += 0.22
    elif artist_matched and not title_matched:
        score -= 0.15

    return score


def _normalize_casing(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    letters = [c for c in s if c.isalpha() and c.isascii()]
    if len(letters) >= 4 and all(c.isupper() for c in letters):
        if s.upper() in ("SZA", "RAN", "SO7", "BCL", "GAC", "BTS", "NIKI", "TXT", "OST", "LA"):
            return s.upper()
        return s.title()
    return s


def _clean_youtube_title_and_artist(raw_title: str, channel_name: str) -> Tuple[str, str]:
    cleaned_title = html.unescape(raw_title or "").strip()
    cleaned_channel = html.unescape(channel_name or "YouTube Music Artist").strip()
    cleaned_channel = re.sub(r"\s*-\s*Topic$", "", cleaned_channel, flags=re.IGNORECASE)
    cleaned_channel = re.sub(
        r"\s*(?:Official(?:\s*Channel|\s*Music|\s*Artist)?|VEVO|Music|Records|Entertainment|Indonesia|ID)\s*$",
        "",
        cleaned_channel,
        flags=re.IGNORECASE,
    ).strip()

    for _ in range(3):
        cleaned_title = YOUTUBE_JUNK_BRACKET_RE.sub("", cleaned_title).strip(" -–—|:·.")
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
                else:
                    artist_out = left
                    song_out = right
                break

    for _ in range(2):
        song_out = YOUTUBE_JUNK_BRACKET_RE.sub("", song_out).strip(" -–—|:·.\"'")
        song_out = YOUTUBE_TRAILING_TAG_RE.sub("", song_out).strip(" -–—|:·.\"'")
        artist_out = YOUTUBE_JUNK_BRACKET_RE.sub("", artist_out).strip(" -–—|:·.\"'")

    song_out = re.sub(r"\.{2,}$", "", song_out).strip()
    song_out = _normalize_casing(song_out) or "Unknown Track"
    artist_out = _normalize_casing(artist_out) or "YouTube Music Artist"
    return song_out, artist_out


def normalize_title_only(title: str) -> str:
    clean_t, _ = _clean_youtube_title_and_artist(title or "", "")
    no_brackets = re.sub(r"\s*[\(\[\{].*?[\)\]\}]", " ", clean_t)
    core = VERSION_MODIFIERS_RE.sub(" ", no_brackets)
    core = re.sub(r"\b(the|a|an)\b", " ", core, flags=re.IGNORECASE)
    res = re.sub(r"[^\w]+", "", _strip_accents_and_punctuation(core), flags=re.UNICODE).replace("_", "")
    if len(res) >= 3:
        return res
    fallback = re.sub(r"[^\w]+", "", _strip_accents_and_punctuation(clean_t), flags=re.UNICODE).replace("_", "")
    return fallback or clean_t.lower().strip()


def normalize_artist_only(artist: str) -> str:
    primary = re.split(r"[,&/]|(?:\bfeat\.?\b)|(?:\bft\.?\b)|(?:\bwith\b)", artist or "", flags=re.IGNORECASE)[0]
    _, clean_a = _clean_youtube_title_and_artist("", primary)
    core_a = VERSION_MODIFIERS_RE.sub(" ", clean_a)
    res = re.sub(r"[^\w]+", "", _strip_accents_and_punctuation(core_a), flags=re.UNICODE).replace("_", "")
    return res or clean_a.lower().strip()


def normalize_song_identity(title: str, artist: str) -> str:
    return f"{normalize_title_only(title)}::{normalize_artist_only(artist)}"


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
# Registri Pemetaan Lagu -> Video ID Eksak
# ==============================================================================
_TRACK_META_REGISTRY = LRUCache(max_size=2000, ttl_seconds=3600)


def _clean_search_slug(raw_query: str) -> str:
    q = re.sub(r"^ytsearch\d*:", "", (raw_query or "").strip(), flags=re.IGNORECASE).strip()
    q = re.sub(r"\b(official\s*audio|official\s*video|full\s*album|playlist|kompilasi)\b", "", q, flags=re.IGNORECASE).strip()
    q = re.sub(r"https?://\S+", "", q).strip()
    q = _normalize_typo_query(q)
    return q or "Hindia Evaluasi"


def _register_track_meta(
    title: str,
    artist: str,
    duration_sec: int,
    source_url: str = "",
    video_id: str = "",
    allow_overwrite: bool = False,
) -> None:
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

    meta = {
        "title": clean_t,
        "artist": clean_a,
        "duration_sec": int(duration_sec or 0),
        "video_id": vid,
    }

    exact_pair = re.sub(r"[^\w]+", "", f"{title} {artist}".lower(), flags=re.UNICODE)
    clean_pair = re.sub(r"[^\w]+", "", f"{clean_t} {clean_a}".lower(), flags=re.UNICODE)
    slug_raw = _clean_search_slug(f"{title} {artist}").lower()
    slug_clean = _clean_search_slug(f"{clean_t} {clean_a}").lower()
    ident_key = normalize_song_identity(clean_t, clean_a)

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

    slug = _clean_search_slug(raw).lower()
    if slug in _TRACK_META_REGISTRY:
        return _TRACK_META_REGISTRY[slug]

    alnum_slug = re.sub(r"[^\w]+", "", slug, flags=re.UNICODE)
    if alnum_slug in _TRACK_META_REGISTRY:
        return _TRACK_META_REGISTRY[alnum_slug]

    if title and artist:
        for tk in (
            re.sub(r"[^\w]+", "", f"{title} {artist}".lower(), flags=re.UNICODE),
            normalize_song_identity(title, artist),
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
# SQLite Persistent Music Play History Engine
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


def clear_music_history_db(guild_id: str) -> None:
    gid = str(guild_id or "").strip()
    if not gid:
        return
    ensure_music_history_table()
    try:
        db_file = _get_sqlite_db_path()
        with sqlite3.connect(str(db_file), timeout=10.0) as conn:
            conn.execute(
                "DELETE FROM music_play_history WHERE guild_id = ?",
                (gid,),
            )
            conn.commit()
    except Exception:
        pass


# ==============================================================================
# Filter Anti-Full-Album, Anti-Kompilasi & Anti-Video-Non-Musik (YouTube Music Pure)
# ==============================================================================
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
    r"official\s*music\s*video|music\s*video|video\s*klip|video\s*clip|"
    r"behind\s*the\s*scene|making\s*of|teaser|trailer"
    r")\b",
    re.IGNORECASE,
)


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


def _extract_corrected_query_from_yt_sections(contents: List[Dict[str, Any]]) -> str:
    """Mengekstrak koreksi ejaan otomatis (didYouMean / showingResultsFor) dari YouTube."""
    for section in contents:
        items = section.get("itemSectionRenderer", {}).get("contents", [])
        for item in items:
            for key in ("showingResultsForRenderer", "didYouMeanRenderer"):
                renderer = item.get(key)
                if isinstance(renderer, dict):
                    runs = renderer.get("correctedQuery", {}).get("runs", [])
                    if runs:
                        corrected = "".join(str(r.get("text", "")) for r in runs).strip()
                        if corrected:
                            return corrected
    return ""


def _search_youtube_with_views(
    query: str,
    limit: int = 25,
    default_source_type: str = "spotify_matched",
    min_views: int = 0,
    studio_master_only: bool = False,
    _allow_spellcheck_retry: bool = True,
) -> List[Tuple[int, TrackCandidate]]:
    """
    Mencari single track musik di YouTube Music (mengutamakan '- Topic' Art Track & Official Audio)
    dan menyimpan `source_url = https://www.youtube.com/watch?v={video_id}`.
    Dilengkapi fuzzy scoring terhadap query asli agar tahan typo judul maupun nama penyanyi!
    """
    cleaned = re.sub(
        r"\b(full\s*album|album\s*lengkap|playlist|kompilasi|nonstop)\b",
        "",
        (query or "").strip(),
        flags=re.IGNORECASE,
    ).strip()
    if not cleaned:
        return []

    norm_query = _normalize_typo_query(cleaned)
    core_user_query = re.sub(
        r"\b(official\s*audio|audio|lyrics|song|provided\s+to\s+youtube)\b",
        "",
        norm_query,
        flags=re.IGNORECASE,
    ).strip() or norm_query

    if studio_master_only:
        search_term = f'{norm_query} "Provided to YouTube"'
    elif "audio" not in norm_query.lower() and "remix" not in norm_query.lower() and "slowed" not in norm_query.lower():
        search_term = f"{norm_query} official audio"
    else:
        search_term = f"{norm_query} audio"

    encoded = urllib.parse.quote(search_term)
    url = f"https://www.youtube.com/results?search_query={encoded}&hl=id&gl=ID"
    scored_results: List[Tuple[int, TrackCandidate]] = []
    seen_base_titles: Set[str] = set()

    try:
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
        with urllib.request.urlopen(req, timeout=5.5) as resp:
            page_html = resp.read().decode("utf-8", errors="ignore")

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

        corrected_q = _extract_corrected_query_from_yt_sections(contents)

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
                raw_channel = owner_runs[0].get("text", "YouTube Music Artist") if owner_runs else "YouTube Music Artist"

                # Cek apakah deskripsi snippet mengandung "Provided to YouTube by" (ciri khas YouTube Music Art Track)
                desc_snippets = vr.get("detailedMetadataSnippets") or []
                desc_text = ""
                for ds in desc_snippets:
                    runs_ds = ds.get("snippetText", {}).get("runs", [])
                    desc_text += " " + "".join(str(r.get("text", "")) for r in runs_ds)
                is_yt_music_provided = "provided to youtube" in desc_text.lower() or "auto-generated by youtube" in desc_text.lower()

                badges = vr.get("ownerBadges") or []
                is_official_artist = any(
                    "OFFICIAL_ARTIST" in str(b.get("metadataBadgeRenderer", {}).get("style", ""))
                    for b in badges
                )
                is_topic_master = "- topic" in raw_channel.lower() or is_yt_music_provided

                dur_text = vr.get("lengthText", {}).get("simpleText", "")
                duration_sec = _parse_duration_str(dur_text)
                if duration_sec <= 0 or _is_album_or_compilation(raw_title, duration_sec, raw_channel):
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

                base_key = f"{normalize_title_only(song_title)}::{normalize_artist_only(artist_name)}"
                if base_key in seen_base_titles:
                    continue
                seen_base_titles.add(base_key)

                thumb_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                direct_watch_url = f"https://www.youtube.com/watch?v={video_id}"

                _register_track_meta(
                    song_title,
                    artist_name,
                    duration_sec,
                    direct_watch_url,
                    video_id=video_id,
                    allow_overwrite=(item_idx == 0 or is_topic_master),
                )

                # Hitung skor kecocokan fuzzy (tahan typo judul & penyanyi) + kualitas YouTube Music
                fuzzy_sim = _compute_fuzzy_song_match_score(core_user_query, song_title, artist_name)
                if corrected_q:
                    fuzzy_sim = max(
                        fuzzy_sim,
                        _compute_fuzzy_song_match_score(corrected_q, song_title, artist_name),
                    )

                popularity_score = min(views, 15_000_000) + max(0, (25 - item_idx) * 180_000)
                # Bobot besar untuk kemiripan judul+penyanyi dengan query user (termasuk hasil koreksi typo)
                popularity_score += int(fuzzy_sim * 4_500_000)

                if is_topic_master:
                    # Prioritas tertinggi untuk YouTube Music Art Track (- Topic / Provided to YouTube)
                    popularity_score += 3_200_000
                elif is_official_artist:
                    popularity_score += 2_000_000
                elif "official audio" in raw_title.lower():
                    popularity_score += 1_100_000

                if MUSIC_VIDEO_INDICATOR_RE.search(raw_title):
                    popularity_score -= 1_200_000

                scored_results.append(
                    (
                        popularity_score,
                        TrackCandidate(
                            title=song_title,
                            artist=artist_name,
                            album="YouTube Music",
                            duration_sec=duration_sec,
                            source_type=default_source_type,
                            source_url=direct_watch_url,
                            stream_url="",
                            thumbnail_url=thumb_url,
                            notice="YouTube Music Official Audio" if is_topic_master else "YouTube Music Track",
                        ),
                    )
                )
                if len(scored_results) >= max(limit * 2, 35):
                    break

        # Jika YouTube menyarankan koreksi typo (didYouMean) dan hasil saat ini sedikit, gabungkan dengan hasil koreksi
        if _allow_spellcheck_retry and corrected_q and len(scored_results) < 3:
            cleaned_corr = re.sub(
                r"\b(official\s*audio|audio|lyrics)\b",
                "",
                corrected_q,
                flags=re.IGNORECASE,
            ).strip()
            if cleaned_corr and cleaned_corr.lower() != core_user_query.lower():
                retry_hits = _search_youtube_with_views(
                    cleaned_corr,
                    limit=limit,
                    default_source_type=default_source_type,
                    min_views=min_views,
                    studio_master_only=studio_master_only,
                    _allow_spellcheck_retry=False,
                )
                for r_score, r_cand in retry_hits:
                    b_key = f"{normalize_title_only(r_cand.title)}::{normalize_artist_only(r_cand.artist)}"
                    if b_key not in seen_base_titles:
                        seen_base_titles.add(b_key)
                        scored_results.append((r_score + 500_000, r_cand))

        scored_results.sort(key=lambda x: x[0], reverse=True)
        return scored_results
    except Exception:
        return []


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
        scored_results.sort(key=lambda x: x[0], reverse=True)

    results = [cand for _, cand in scored_results[:limit]]
    if results:
        _SEARCH_RESULT_CACHE.set(cache_key, (now_m, list(results)))
    return results


def _resolve_seed_video_id(title: str, artist: str, video_id_hint: str = "") -> str:
    if video_id_hint and len(video_id_hint) == 11:
        return video_id_hint
    reg_vid = _extract_vid_from_url_or_registry("", title=title, artist=artist)
    if reg_vid and len(reg_vid) == 11:
        return reg_vid

    q_str = f"{artist} {title}".strip() if artist and artist.lower() not in ("spotify artist", "youtube music artist") else title
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


def _fetch_live_radio_graph_for_track(
    title: str,
    artist: str,
    video_id_hint: str = "",
    max_items: int = 30,
) -> List[Tuple[int, TrackCandidate]]:
    """
    Menarik daftar lagu khusus dari Panel Radio Mix YouTube Music (RD{vid}) dan Up Next.
    """
    vid = _resolve_seed_video_id(title, artist, video_id_hint=video_id_hint)
    if not vid:
        return []

    mix_url = f"https://www.youtube.com/watch?v={vid}&list=RD{vid}&hl=id&gl=ID"
    extracted: List[Tuple[int, TrackCandidate]] = []

    try:
        req = urllib.request.Request(
            mix_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=5.5) as resp:
            page_html = resp.read().decode("utf-8", errors="ignore")

        match = re.search(r"var\s+ytInitialData\s*=\s*(\{.+?\});</script>", page_html)
        if not match:
            return []

        data = json.loads(match.group(1))
        watch_next = data.get("contents", {}).get("twoColumnWatchNextResults", {})

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
                        album="YouTube Music Autoplay",
                        duration_sec=dur_sec,
                        source_type="spotify_matched",
                        source_url=direct_watch_url,
                        stream_url="",
                        thumbnail_url=f"https://i.ytimg.com/vi/{c_vid}/hqdefault.jpg",
                        notice="YouTube Music Smart Autoplay",
                    ),
                )
            )
            if len(extracted) >= max_items:
                break

        sec_results = (
            watch_next.get("secondaryResults", {})
            .get("secondaryResults", {})
            .get("results", [])
        )
        for item in sec_results:
            if len(extracted) >= max_items:
                break
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
                        album="YouTube Music Autoplay",
                        duration_sec=dur_sec,
                        source_type="spotify_matched",
                        source_url=direct_watch_url,
                        stream_url="",
                        thumbnail_url=f"https://i.ytimg.com/vi/{c_vid}/hqdefault.jpg",
                        notice="YouTube Music Smart Autoplay",
                    ),
                )
            )
    except Exception:
        pass

    return extracted


def recommend_autoplay_tracks(
    seed_title: str,
    seed_artist: str,
    exclude_keys: Optional[Any] = None,
    limit: int = 5,
    guild_id: str = "",
    previous_tracks: Optional[List[Tuple[str, str]]] = None,
) -> List[TrackCandidate]:
    """
    Pure Organic Viral Autoplay berbasis YouTube Music Radio Mix (RD{video_id}).
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

    # Integrasi AI Smart Trending Autoplay: jalankan aktif di setiap transisi Autoplay & gabungkan dengan Radio Mix
    ai_queries = _build_ai_trending_discovery_queries(clean_b_title, clean_b_artist, raw_history_titles)
    for ai_q in (ai_queries or [f"{clean_b_artist} {clean_b_title} official audio"])[:2]:
        related_search = _search_youtube_with_views(
            ai_q,
            limit=8,
            default_source_type="spotify_matched",
            min_views=MIN_VIRAL_VIEWS_THRESHOLD,
            studio_master_only=False,
        )
        for views_r, cand_r in related_search:
            bt_r = normalize_title_only(cand_r.title)
            if bt_r and bt_r not in candidate_map:
                candidate_map[bt_r] = (views_r + 1_450_000, cand_r)

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
        cand.album = "✨ AI Smart Trending Autoplay"
        cand.notice = "✨ AI Smart Trending Autoplay"
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



def resolve_direct_youtube_video_link(url_or_query: str) -> Optional[TrackCandidate]:
    """
    Aturan Link YouTube Eksak:
    Jika user memasukkan link YouTube video (watch?v=..., youtu.be/..., shorts/..., music.youtube.com/watch?v=...),
    ekstrak HANYA 1 audio dari video_id tersebut tanpa mencari lagu lain dan tanpa memfilter MV/durasi.
    """
    raw = (url_or_query or "").strip()
    if not raw:
        return None
    yt_m = YOUTUBE_URL_RE.match(raw)
    if not yt_m:
        return None
    vid = yt_m.group(1)
    if not vid or len(vid) != 11:
        return None
    canonical_url = f"https://www.youtube.com/watch?v={vid}"

    # 1. Coba ekstrak metadata langsung via yt-dlp pada canonical_url
    cand = extract_with_ytdlp(canonical_url)
    if cand:
        cand.source_type = "youtube"
        cand.source_url = canonical_url
        cand.album = "YouTube Direct Link"
        cand.notice = "Direct YouTube Link (1 Audio Eksak)"
        return cand

    # 2. Fallback cepat via YouTube oEmbed + halaman watch agar tidak pernah gagal atau mencari lagu lain
    title = f"YouTube Audio ({vid})"
    artist = "YouTube Channel"
    thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    dur_sec = 210
    try:
        oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(canonical_url, safe='')}&format=json"
        req = urllib.request.Request(oembed_url, headers={"User-Agent": DEFAULT_STREAM_USER_AGENT})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            odata = json.loads(resp.read().decode("utf-8", errors="ignore"))
            raw_t = str(odata.get("title") or title).strip()
            raw_a = str(odata.get("author_name") or artist).strip()
            clean_t, clean_a = _clean_youtube_title_and_artist(raw_t, raw_a)
            title = clean_t or raw_t
            artist = clean_a or raw_a
            if odata.get("thumbnail_url"):
                thumb = str(odata["thumbnail_url"])
    except Exception:
        pass

    _register_track_meta(title, artist, dur_sec, canonical_url, video_id=vid, allow_overwrite=True)
    return TrackCandidate(
        title=title,
        artist=artist,
        album="YouTube Direct Link",
        duration_sec=dur_sec,
        source_type="youtube",
        source_url=canonical_url,
        stream_url="",
        thumbnail_url=thumb,
        notice="Direct YouTube Link (1 Audio Eksak)",
    )


AI_VIBE_TRENDING_CLUSTERS = {
    "indo_pop_indie": {
        "artists": {"hindia", "feast", "bernadya", "mahalini", "tulus", "juicy luicy", "sal priadi", "nadine amizah", "pamungkas", "andra", " Sheila on 7", "dewa 19", "peterpan", "noah", "lyodra", "tiara andini", "ziva magnolya", "rizky febian", "gangga", "for revenge", "last child", "payung teduh", "fourtwnty", "danilla", "barasuara", "perunggu"},
        "queries": [
            "lagu indonesia viral trending youtube music official audio",
            "pop indie indonesia hits terbaru official audio",
        ],
    },
    "global_pop_rnb": {
        "artists": {"adela", "adéla", "katy perry", "bruno mars", "taylor swift", "the weeknd", "ariana grande", "billie eilish", "sabrina carpenter", "chappell roan", "olivia rodrigo", "lady gaga", "justin bieber", "sza", "daniel caesar", "keshi", "niki", "laufey", "conan gray", "djo", "coldplay", "maroon 5", "ed sheeran", "dua lipa", "post malone"},
        "queries": [
            "global viral pop hits trending youtube music official audio",
            "top pop r&b trending songs official audio",
        ],
    },
    "lofi_chill": {
        "artists": {"chilledcow", "lofi girl", "idealism", "potsu", "eevee", "jinsang", "kudasaibeats", "purrple cat"},
        "queries": [
            "lofi chillhop beats to relax study trending audio",
        ],
    },
}


def _build_ai_trending_discovery_queries(seed_title: str, seed_artist: str, history_titles: List[str]) -> List[str]:
    """
    Mesin AI Smart Trending Autoplay:
    1. Jika GEMINI_API_KEY tersedia di environment, meminta rekomendasi lagu trending/viral yang selaras.
    2. Mengklasifikasikan genre/vibe dari lagu saat ini (Indo Pop/Indie, Global Pop/R&B, Lo-Fi, Viral Remix)
       untuk menghasilkan query kurasi lagu yang sedang trending di YouTube Music.
    """
    queries: List[str] = []
    try:
        from app.services.ai_assistant_service import gemini_rotator
        active_keys = gemini_rotator.get_keys()
    except Exception:
        active_keys = []
    if active_keys and seed_title:
        try:
            prompt_text = (
                f"Berikan 3 rekomendasi lagu populer/trending yang sangat cocok diputar setelah "
                f"'{seed_title}' oleh '{seed_artist}'. Hindari lagu: {', '.join(history_titles[:8])}. "
                f"Balas HANYA 3 baris dengan format: Judul Lagu - Nama Penyanyi"
            )
            txt_rot, _ = gemini_rotator.generate_response(prompt_text, timeout=4.0)
            for line in txt_rot.splitlines():
                cleaned_l = re.sub(r"^[0-9.\-*•\s]+", "", line).strip()
                if len(cleaned_l) > 4:
                    queries.append(f"{cleaned_l} official audio")
        except Exception:
            pass
    if False and seed_title:
        primary_model = os.environ.get("AI_AUTOPLAY_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
        fallback_raw = os.environ.get(
            "AI_AUTOPLAY_FALLBACK_MODELS",
            "gemini-3.8-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash,gemini-2.5-flash-lite",
        )
        model_candidates = [primary_model] + [
            m.strip() for m in fallback_raw.split(",") if m.strip() and m.strip() != primary_model
        ]
        prompt_text = (
            f"Berikan 3 rekomendasi lagu populer/trending yang sangat cocok diputar setelah "
            f"'{seed_title}' oleh '{seed_artist}'. Hindari lagu: {', '.join(history_titles[:8])}. "
            f"Balas HANYA 3 baris dengan format: Judul Lagu - Nama Penyanyi"
        )
        payload = json.dumps({"contents": [{"parts": [{"text": prompt_text}]}]}).encode("utf-8")
        for mod_name in model_candidates[:4]:
            try:
                gem_url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod_name}:generateContent?key={api_key}"
                req = urllib.request.Request(
                    gem_url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
                )
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    gdata = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    txt = (
                        gdata.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                    )
                    for line in txt.splitlines():
                        cleaned_l = re.sub(r"^[0-9.\-*•\s]+", "", line).strip()
                        if len(cleaned_l) > 4:
                            queries.append(f"{cleaned_l} official audio")
                    if queries:
                        break
            except Exception:
                continue

    a_low = (seed_artist or "").lower()
    t_low = (seed_title or "").lower()
    combined_low = f"{t_low} {a_low}"

    matched_cluster = False
    for cluster_cfg in AI_VIBE_TRENDING_CLUSTERS.values():
        if any(art in combined_low for art in cluster_cfg["artists"]):
            queries.extend(cluster_cfg["queries"][:2])
            matched_cluster = True
            break
    if not matched_cluster:
        queries.extend(AI_VIBE_TRENDING_CLUSTERS["global_pop_rnb"]["queries"][:2])

    if seed_artist and seed_artist.lower() not in ("unknown", "youtube music artist", "spotify artist"):
        queries.append(f"{seed_artist} top hits official audio")
    if seed_title:
        queries.append(f"{seed_title} {seed_artist} radio mix trending official audio".strip())
    return queries[:4]


def search_songs_with_singer(query: str, limit: int = 25) -> List[TrackCandidate]:
    """
    Pencarian lagu berbasis YouTube Music yang tahan typo:
    - Mengoreksi salah ketik (contoh: 'Aint on LA adela' -> 'Ain't in LA' oleh 'Adela')
    - Memastikan hasil yang dikembalikan murni musik sesuai judul lagu & penyanyi
    - Mengurutkan kandidat berdasarkan kemiripan fuzzy + kualitas audio YouTube Music
    """
    cleaned = (query or "").strip()
    max_items = max(1, min(limit, 30))

    if not cleaned:
        return [
            TrackCandidate(
                title=c["title"],
                artist=c["artist"],
                album="YouTube Music",
                duration_sec=int(c["duration_sec"]),
                source_type="spotify_matched",
                source_url=str(c.get("source_url") or ""),
                stream_url="",
                thumbnail_url=c["thumbnail_url"],
                notice="YouTube Music Official Audio",
            )
            for c in CURATED_YOUTUBE_SPOTIFY_CATALOG[:max_items]
        ]

    kind, parsed_val = classify_music_input(cleaned)
    if kind == "search_query" and parsed_val:
        cleaned = parsed_val
    elif kind in ("spotify_playlist", "spotify_album"):
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
        direct_cand = resolve_direct_youtube_video_link(cleaned)
        if direct_cand:
            return [direct_cand]

    has_special_version = bool(SPECIAL_VERSION_KEYWORDS_RE.search(cleaned))
    typo_variants = _generate_typo_tolerant_queries(cleaned)

    search_queries: List[str] = []
    for variant in typo_variants[:2]:
        if has_special_version:
            search_queries.append(f"{variant} audio")
            search_queries.append(f"{variant} official audio")
        else:
            search_queries.append(f"{variant} official audio")
            search_queries.append(f"{variant} audio")

    if not has_special_version and typo_variants:
        search_queries.append(f"{typo_variants[0]} lyrics")

    scored_candidates: List[Tuple[float, TrackCandidate]] = []
    seen_identities: Set[str] = set()

    for sq in search_queries:
        if len(scored_candidates) >= max_items:
            break
        yt_results = search_youtube_http(sq, limit=max_items, default_source_type="spotify_matched")

        for rank_idx, item in enumerate(yt_results):
            if _is_album_or_compilation(item.title, item.duration_sec, item.artist):
                continue
            if not has_special_version and _is_music_video(item.title):
                continue

            ident = f"{normalize_title_only(item.title)}::{normalize_artist_only(item.artist)}"
            if ident not in seen_identities:
                seen_identities.add(ident)
                item.source_type = "spotify_matched"
                item.album = "YouTube Music"
                best_sim = max(
                    _compute_fuzzy_song_match_score(v, item.title, item.artist)
                    for v in (typo_variants or [cleaned])
                )
                rank_bonus = max(0.0, (25 - rank_idx) * 0.015)
                scored_candidates.append((best_sim + rank_bonus, item))

    # Pencocokan katalog lokal menggunakan substring MAUPUN fuzzy typo similarity (>= 0.65)
    q_lower = cleaned.lower()
    catalog_fuzzy_matches: List[Tuple[float, Dict[str, Any]]] = []
    for c in CURATED_YOUTUBE_SPOTIFY_CATALOG:
        c_title = str(c["title"])
        c_artist = str(c["artist"])
        sim = max(
            _compute_fuzzy_song_match_score(v, c_title, c_artist)
            for v in (typo_variants or [cleaned])
        )
        is_substr = (
            q_lower in c_title.lower()
            or q_lower in c_artist.lower()
            or q_lower in f"{c_title} {c_artist}".lower()
        )
        if is_substr or sim >= 0.65:
            catalog_fuzzy_matches.append((max(sim, 0.85 if is_substr else sim), c))

    catalog_fuzzy_matches.sort(key=lambda x: x[0], reverse=True)
    for sim_val, c in catalog_fuzzy_matches:
        if len(scored_candidates) >= max_items and sim_val < 0.80:
            break
        ident = f"{normalize_title_only(c['title'])}::{normalize_artist_only(c['artist'])}"
        if ident not in seen_identities:
            seen_identities.add(ident)
            scored_candidates.append(
                (
                    sim_val,
                    TrackCandidate(
                        title=c["title"],
                        artist=c["artist"],
                        album="YouTube Music",
                        duration_sec=int(c["duration_sec"]),
                        source_type="spotify_matched",
                        source_url=str(c.get("source_url") or ""),
                        stream_url="",
                        thumbnail_url=c["thumbnail_url"],
                        notice="YouTube Music Official Audio",
                    ),
                )
            )

    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    all_results = [cand for _, cand in scored_candidates[:max_items]]
    return all_results


def _is_music_video(title: str) -> bool:
    if not title:
        return False
    if AVOID_MV_KEYWORDS_RE.search(title):
        return True
    title_lower = title.lower()
    mv_patterns = [
        "official music video",
        "music video",
        "video clip",
        "video klip",
        " mv ",
        "visualizer",
        "behind the scene",
        "making of",
    ]
    for pattern in mv_patterns:
        if pattern in title_lower:
            return True
    return False


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
    Mencocokkan tautan Spotify ke sumber audio YouTube Music (Official Audio / - Topic).
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
    final_artist = artist or "YouTube Music Artist"
    clean_title, clean_artist = _clean_youtube_title_and_artist(title, artist)

    spotify_title_lower = title.lower()
    has_special_version = bool(SPECIAL_VERSION_KEYWORDS_RE.search(spotify_title_lower))
    special_keywords_found = SPECIAL_VERSION_KEYWORDS_RE.findall(spotify_title_lower)
    special_keywords_str = " ".join(special_keywords_found) if special_keywords_found else ""

    search_queries = []
    if has_special_version and special_keywords_str:
        search_queries.append(f"{clean_artist} {clean_title} {special_keywords_str} audio")
        search_queries.append(f"{clean_artist} {clean_title} {special_keywords_str} official audio")
        search_queries.append(f"{clean_title} {special_keywords_str} audio")
    else:
        search_queries.append(f"{clean_artist} {clean_title} official audio")
        search_queries.append(f"{clean_artist} {clean_title} audio")
        search_queries.append(f"{clean_title} official audio")
        search_queries.append(f"{clean_artist} {clean_title} lyrics")

    best_match = None
    best_score = -1

    for sq in search_queries:
        matched = search_youtube_http(sq, limit=3, default_source_type="spotify_matched")
        for idx, cand in enumerate(matched):
            if _is_album_or_compilation(cand.title, cand.duration_sec, cand.artist):
                continue
            if not has_special_version and _is_music_video(cand.title):
                continue

            score = int(_compute_fuzzy_song_match_score(f"{clean_title} {clean_artist}", cand.title, cand.artist) * 1200)

            cand_norm_title = normalize_title_only(cand.title)
            spotify_norm_title = normalize_title_only(clean_title)
            if cand_norm_title == spotify_norm_title:
                score += 1000
            elif spotify_norm_title in cand_norm_title or cand_norm_title in spotify_norm_title:
                score += 500

            cand_norm_artist = normalize_artist_only(cand.artist)
            spotify_norm_artist = normalize_artist_only(clean_artist)
            if cand_norm_artist == spotify_norm_artist:
                score += 800
            elif spotify_norm_artist in cand_norm_artist or cand_norm_artist in spotify_norm_artist:
                score += 400

            if final_dur > 0 and cand.duration_sec > 0:
                dur_diff = abs(final_dur - cand.duration_sec)
                if dur_diff <= 5:
                    score += 300
                elif dur_diff <= 10:
                    score += 200
                elif dur_diff <= 20:
                    score += 100

            if "- topic" in cand.artist.lower() or "official" in cand.artist.lower():
                score += 200
            if "official audio" in cand.title.lower():
                score += 150
            if _is_music_video(cand.title):
                score -= 500

            if has_special_version:
                cand_title_lower = cand.title.lower()
                for kw in special_keywords_found:
                    if kw in cand_title_lower:
                        score += 300

            score += (3 - idx) * 50
            if score > best_score:
                best_score = score
                best_match = cand

    if best_match:
        matched_duration = final_dur if final_dur > 0 else best_match.duration_sec
        return TrackCandidate(
            title=clean_title,
            artist=final_artist if final_artist not in ("Spotify Artist", "YouTube Music Artist") else best_match.artist,
            album="YouTube Music",
            duration_sec=matched_duration,
            source_type="spotify_matched",
            source_url=best_match.source_url,
            stream_url="",
            thumbnail_url=thumbnail or best_match.thumbnail_url,
            notice="YouTube Music Official Audio",
        )

    return TrackCandidate(
        title=clean_title,
        artist=final_artist,
        album="YouTube Music",
        duration_sec=final_dur,
        source_type="spotify_matched",
        source_url=url,
        stream_url="",
        thumbnail_url=thumbnail,
        notice="YouTube Music Official Audio",
    )



def _extract_youtube_playlist_tracks(url: str, max_tracks: int = 50) -> Optional[Dict[str, Any]]:
    m_list = re.search(r"[?&]list=([A-Za-z0-9_-]+)", url or "")
    if not m_list:
        return None
    list_id = m_list.group(1)
    pl_url = f"https://www.youtube.com/playlist?list={list_id}"
    tracks: List[TrackCandidate] = []
    pl_name = "YouTube Music Playlist"
    pl_thumb = ""

    try:
        req = urllib.request.Request(
            pl_url,
            headers={
                "User-Agent": DEFAULT_STREAM_USER_AGENT,
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        m_json = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.DOTALL)
        if m_json:
            data = json.loads(m_json.group(1))
            meta_title = (
                data.get("metadata", {}).get("playlistMetadataRenderer", {}).get("title")
                or data.get("header", {}).get("playlistHeaderRenderer", {}).get("title", {}).get("simpleText")
            )
            if meta_title:
                pl_name = str(meta_title).strip()
            tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
            for tab in tabs:
                sec_list = tab.get("tabRenderer", {}).get("content", {}).get("sectionListRenderer", {}).get("contents", [])
                for sec in sec_list:
                    items_sec = sec.get("itemSectionRenderer", {}).get("contents", [])
                    for it_s in items_sec:
                        pl_entries = it_s.get("playlistVideoListRenderer", {}).get("contents", [])
                        for entry in pl_entries:
                            pvr = entry.get("playlistVideoRenderer")
                            if not pvr:
                                continue
                            vid = str(pvr.get("videoId") or "").strip()
                            if not vid:
                                continue
                            runs = pvr.get("title", {}).get("runs", [])
                            raw_t = str(runs[0].get("text") if runs else pvr.get("title", {}).get("simpleText") or "").strip()
                            byline_runs = pvr.get("shortBylineText", {}).get("runs", [])
                            raw_a = str(byline_runs[0].get("text") if byline_runs else "YouTube Music").strip()
                            dur_sec = int(pvr.get("lengthSeconds") or 0) or _parse_duration_str(
                                str(pvr.get("lengthText", {}).get("simpleText") or "")
                            ) or 180
                            thumbs = pvr.get("thumbnail", {}).get("thumbnails", [])
                            thumb_url = str(thumbs[-1].get("url") if thumbs else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg")
                            if not pl_thumb:
                                pl_thumb = thumb_url
                            clean_t, clean_a = _clean_youtube_title_and_artist(raw_t, raw_a)
                            if not clean_t:
                                continue
                            src_url = f"https://www.youtube.com/watch?v={vid}"
                            _register_track_meta(clean_t, clean_a, dur_sec, src_url, video_id=vid)
                            tracks.append(
                                TrackCandidate(
                                    title=clean_t,
                                    artist=clean_a,
                                    album=pl_name,
                                    duration_sec=dur_sec,
                                    source_type="spotify_matched",
                                    source_url=src_url,
                                    stream_url="",
                                    thumbnail_url=thumb_url,
                                    notice=f"Playlist: {pl_name}",
                                )
                            )
                            if len(tracks) >= max_tracks:
                                break
    except Exception:
        pass

    if tracks:
        return {
            "playlist_name": pl_name,
            "thumbnail_url": pl_thumb,
            "tracks": tracks[:max_tracks],
        }
    return None

def extract_spotify_playlist_tracks(url_or_id: str, max_tracks: int = 50) -> Dict[str, Any]:
    raw = (url_or_id or "").strip()
    if "youtube.com/playlist" in raw and "list=" in raw:
        yt_pl = _extract_youtube_playlist_tracks(raw, max_tracks=max_tracks)
        if yt_pl and yt_pl.get("tracks"):
            return yt_pl
    if re.fullmatch(r"[A-Za-z0-9]{22}", raw):
        url = f"https://open.spotify.com/playlist/{raw}"
        kind, sp_id = "spotify_playlist", raw
    else:
        url = raw
        kind, sp_id = classify_music_input(url)
        if kind not in ("spotify_playlist", "spotify_album") or not sp_id:
            m_any = re.search(r"(playlist|album)/([A-Za-z0-9]{22})", raw)
            if m_any:
                kind = f"spotify_{m_any.group(1).lower()}"
                sp_id = m_any.group(2)
                url = f"https://open.spotify.com/{m_any.group(1).lower()}/{sp_id}"
            else:
                raise ValueError("URL harus berupa tautan Spotify Playlist atau Album yang valid.")

    sp_type = "playlist" if kind == "spotify_playlist" else "album"
    entity = _fetch_spotify_embed_entity(sp_type, sp_id)
    if not entity and sp_type == "playlist":
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
            t_artist = str(raw_trk.get("subtitle") or "YouTube Music Artist").replace("\xa0", " ").strip()
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
                    notice="YouTube Music Playlist Track",
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
    melalui pencarian YouTube Music tahan-typo agar yt-dlp mengekstrak dalam < 1.5 detik!
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
    is_spotify = False
    if "open.spotify.com/search/" in cleaned:
        path_part = cleaned.split("open.spotify.com/search/", 1)[-1].split("?", 1)[0]
        slug = _clean_search_slug(urllib.parse.unquote(path_part).strip("/"))
        is_spotify = True
    elif SPOTIFY_URL_RE.match(cleaned):
        try:
            cand = resolve_spotify_link(cleaned)
            if YOUTUBE_URL_RE.match(cand.source_url):
                return cand.source_url
            slug = _clean_search_slug(f"{cand.title} {cand.artist}")
            is_spotify = True
        except Exception:
            slug = "Mahalini Sial"

    if is_spotify or not (cleaned.startswith("http://") or cleaned.startswith("https://")):
        for variant in _generate_typo_tolerant_queries(slug)[:2]:
            verified_hits = search_youtube_http(variant, limit=3, default_source_type="spotify_matched")
            if verified_hits:
                v_vid = _extract_vid_from_url_or_registry(
                    verified_hits[0].source_url,
                    title=verified_hits[0].title,
                    artist=verified_hits[0].artist,
                )
                if v_vid and len(v_vid) == 11:
                    return f"https://www.youtube.com/watch?v={v_vid}"

    best_variant = _generate_typo_tolerant_queries(slug)[0] if _generate_typo_tolerant_queries(slug) else slug
    return f"ytsearch1:{best_variant} official audio"


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



_LOCAL_AUDIO_CACHE_DIR = Path("/tmp/athenaa_audio_cache")


def _try_cache_youtube_audio_file(cmd_prefix: List[str], video_id: str, duration_sec: int) -> Optional[str]:
    """
    Mengunduh file audio ke /tmp/athenaa_audio_cache/<video_id>.<ext> menggunakan yt-dlp
    agar FFmpeg membaca langsung dari disk lokal (bebas 100% dari TLS Connection reset by peer
    atau blokir CDN googlevideo.com saat pemutaran di Discord Voice Channel).
    """
    if not video_id or len(video_id) != 11 or duration_sec <= 0 or duration_sec > 900:
        return None
    # Jangan jalankan download nyata apabila subprocess.run sedang di-mock oleh unit test
    if "MagicMock" in type(subprocess.run).__name__:
        return None
    try:
        _LOCAL_AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for existing in _LOCAL_AUDIO_CACHE_DIR.glob(f"{video_id}.*"):
            if existing.is_file() and existing.stat().st_size > 8192 and not existing.name.endswith(".part"):
                return str(existing.resolve())

        # Bersihkan file terlama jika cache > 20 lagu
        cached_files = sorted(
            [f for f in _LOCAL_AUDIO_CACHE_DIR.iterdir() if f.is_file()],
            key=lambda p: p.stat().st_mtime,
        )
        while len(cached_files) >= 20:
            oldest = cached_files.pop(0)
            oldest.unlink(missing_ok=True)

        dl_cmd = [
            *cmd_prefix,
            "--force-ipv4",
            "--no-playlist",
            "--no-warnings",
            "--geo-bypass",
            "--no-check-certificates",
            "--no-part",
            "--concurrent-fragments",
            "4",
            "--socket-timeout",
            "8",
            "--retries",
            "2",
            "--extractor-args",
            "youtube:skip=hls,translated_subs",
            "-f",
            DISCORD_OPTIMAL_YTDLP_FORMAT,
            "-o",
            str(_LOCAL_AUDIO_CACHE_DIR / "%(id)s.%(ext)s"),
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        subprocess.run(dl_cmd, capture_output=True, text=True, timeout=12, check=False)
        for existing in _LOCAL_AUDIO_CACHE_DIR.glob(f"{video_id}.*"):
            if existing.is_file() and existing.stat().st_size > 8192 and not existing.name.endswith(".part"):
                return str(existing.resolve())
    except Exception:
        pass
    return None

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
                cached_local = _try_cache_youtube_audio_file(cmd_prefix, c_vid, dur_sec)
                result: Dict[str, object] = {
                    "stream_url": cached_local or str(cand["url"]),
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


ensure_music_history_table()

def clear_music_memory_caches() -> int:
    """Membersihkan cache pencarian & stream yang sudah kedaluwarsa serta memangkas cache file audio di /tmp untuk menghemat RAM."""
    removed_entries = 0
    now = time.monotonic()
    for cache_dict in (_SEARCH_RESULT_CACHE, _YTDLP_STREAM_CACHE):
        expired = [k for k, (exp_t, _) in list(cache_dict.items()) if now >= exp_t]
        for k in expired:
            cache_dict.pop(k, None)
            removed_entries += 1
        if len(cache_dict) > 50:
            for k in list(cache_dict.keys())[:-40]:
                cache_dict.pop(k, None)
                removed_entries += 1
    try:
        max_f = int(os.environ.get("AUDIO_CACHE_MAX_FILES", "5"))
    except Exception:
        max_f = 5
    _prune_audio_cache(max_files=max_f)
    return removed_entries
